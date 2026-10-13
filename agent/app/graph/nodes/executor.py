# app/graph/nodes/executor.py
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_core.runnables import RunnableConfig

from app.graph.state import AgentState
from app.graph.config import (
    get_llm_instance,
    get_cached_bound_llm,
    invoke_llm_with_limit,
    _resolve_provider_and_key,
)
from app.graph.utils import (
    update_token_usage,
    prune_messages_by_token_limit,
    _build_task_context,
    load_agent_manifest_instructions,
)
from app.core.settings import settings
from app.core.logger import setup_app_logger

logger = setup_app_logger("CognitiveNodes")

COMPACT_AGENT_REMINDER = "REMINDER: Output ONLY the JSON/Markdown block. No pleasantries. Think step-by-step but keep thoughts under 2 sentences."


def _sanitize_orphaned_tool_calls(messages: list) -> list:
    """
    Removes or neutralizes AIMessages that have tool_calls but lack a corresponding ToolMessage.
    This occurs when evaluate_tool_hooks short-circuits to finding_extractor (e.g. safeguard triggered).
    OpenAI/Anthropic strictly require every tool_call_id to be followed by a ToolMessage.
    """
    sanitized = []
    i = 0
    while i < len(messages):
        msg = messages[i]
        # Check for AIMessages with tool_calls that were not responded to
        if hasattr(msg, 'tool_calls') and msg.tool_calls:
            tool_call_ids = {tc['id'] for tc in msg.tool_calls}
            # Look for corresponding ToolMessages in the remaining history
            remaining = messages[i + 1:]
            responded_ids = {
                getattr(m, 'tool_call_id', None)
                for m in remaining
                if getattr(m, 'tool_call_id', None)
            }
            orphaned = tool_call_ids - responded_ids
            if orphaned:
                logger.warning(
                    f"[MessageSanitizer] Removing orphaned tool_calls {orphaned} "
                    f"from AIMessage (safeguard short-circuit). "
                    f"Preserving text content if present."
                )
                # Keep the text content if available, discard tool_calls
                text_content = msg.content if isinstance(msg.content, str) else ""
                if text_content.strip():
                    sanitized.append(AIMessage(content=text_content))
                # Skip the entire message if there is no text content
                i += 1
                continue
        sanitized.append(msg)
        i += 1
    return sanitized


async def node_support_agent(state: AgentState, config: RunnableConfig = None):
    """
    Node: SUPPORT_AGENT.
    Specialized agent for answering questions about website operations (UI/navigation).
    Only has access to read the user manual from the database (via Qdrant/Tool).
    Strictly forbidden from answering security or backend architecture queries.
    """
    user_latest_message = state["messages"][-1].content
    logger.info(f"==> [Support Agent] Handling navigation FAQ: '{user_latest_message[:50]}...'")

    support_system_prompt = (
        "You are a Customer Support Specialist for the hotel booking system. "
        "Your only task is to answer questions and guide users on how to use the website "
        "(e.g., how to book a room, update personal info, view booking history, cancel a booking, etc.).\n\n"
        "CRITICAL RULES:\n"
        "1. You MUST ONLY rely on the knowledge provided in the Database (via the user guide document search tool) to answer.\n"
        "2. You are STRICTLY FORBIDDEN from performing any Web Search (e.g., Tavily, Google).\n"
        "3. ABSOLUTELY DO NOT disclose any information regarding system architecture, backend logic, database structure, or security issues. "
        "If a user asks about system architecture or security, you must politely decline by saying: "
        "'I apologize, but I am only a website usage assistant and I am not permitted to provide information regarding system architecture or security.'\n"
        "4. Always keep your answers concise, polite, and accurate, matching the user's language."
    )

    llm = get_llm_instance(1, config)

    # Support agent intentionally has no tools — uses system prompt only
    # Do NOT call get_cached_bound_llm here; it would bind travel/search tools incorrectly
    bound_llm = llm

    response, usage = await invoke_llm_with_limit(
        1, bound_llm, [
            SystemMessage(content=support_system_prompt),
            HumanMessage(content=user_latest_message)
        ], config, max_tokens_override=settings.node_limits.support_agent, node_name="support_agent"
    )

    # Convert ToolMessage handling or just return AIMessage if it directly responds
    return {
        "messages": [response],
        **update_token_usage(state, usage, node_name="support_agent")
    }


async def node_travel_react_agent(state: AgentState, config: RunnableConfig = None):
    """
    Node: TRAVEL_REACT_AGENT.
    Operating as a true topological ReAct Agent specifically for Travel tasks.
    """
    user_id = state.get("user_id", "UNKNOWN_USER")
    intent_category = state.get("intent_category", "travel_faq")

    user_initial_prompt = state["messages"][0].content if state["messages"] else ""
    manifest = load_agent_manifest_instructions()
    task_context = _build_task_context(state)

    if intent_category == "hotel_booking":
        intent_instructions = "Focus heavily on providing accurate dates, pricing, and precise location details for hotels."
    elif intent_category == "itinerary_planning":
        intent_instructions = "Provide logical sequential progression in the plans. Include estimated travel times and distances."
    else:
        intent_instructions = "Rely on the travel knowledge base for factual, up-to-date responses."

    system_content = (
        f"{manifest}\n\n"
        f"You are the TRAVEL_REACT_AGENT operating in a Reason-and-Act (ReAct) loop.\n"
        f"Current task intent: {intent_category.upper()}\n"
        f"Directives: {intent_instructions}\n\n"
        "Follow this execution cycle:\n"
        "1. THOUGHT: Think step-by-step about the user's travel request and current state.\n"
        "2. ACTION: If you need external data (hotel info, flights), invoke the appropriate tool.\n"
        "3. OBSERVATION: The system will execute your tool and append a ToolMessage.\n"
        "4. EVALUATION: If the observation is insufficient, form a new THOUGHT and ACTION.\n"
        "5. FINAL ANSWER: Once you have sufficient information, write a complete, well-structured "
        "Markdown response.\n\n"
        "CRITICAL RULE: CRITIC BEFORE TOOL. Do I actually need external data, or can I deduce it from context?\n"
    )

    if task_context:
        system_content += f"<current_task>\n{task_context}\n</current_task>\n\n"

    compiled_messages = [SystemMessage(content=system_content)]
    compiled_messages.extend(state["messages"])
    compiled_messages = _sanitize_orphaned_tool_calls(compiled_messages)

    base_llm = get_llm_instance(2, config)
    llm_with_tools = get_cached_bound_llm("travel", base_llm)

    provider, provider_cfg, _ = _resolve_provider_and_key(config)

    compiled_messages = prune_messages_by_token_limit(
        compiled_messages,
        provider_cfg.max_context_tokens,
        provider_cfg.tier2_balanced_model
    )

    current_iteration = state.get("iteration_count", 0) + 1

    if current_iteration > 1:
        compiled_messages.append(SystemMessage(content=COMPACT_AGENT_REMINDER))

    response, usage = await invoke_llm_with_limit(2, llm_with_tools, compiled_messages, config, max_tokens_override=settings.node_limits.travel_react_agent, node_name="travel_react_agent")
    return {
        "messages": [response],
        "iteration_count": current_iteration,
        **update_token_usage(state, usage, node_name="travel_react_agent")
    }


async def node_clarification_agent(state: AgentState, config: RunnableConfig = None):
    """
    Triggered when intent_confidence < INTENT_CONFIDENCE_THRESHOLD.
    Generates a natural clarification question.
    """
    user_message = state["messages"][-1].content
    ambiguity_reason = state.get("ambiguity_reason", "The request was unclear.")
    detected_language = state.get("detected_language", "English")

    clarification_prompt = f"""
    You are a friendly Travel Assistant. The user's request is ambiguous.
    Ambiguity reason: {ambiguity_reason}
    
    Generate ONE natural clarification question in {detected_language}.
    Offer 2-3 specific options to help user clarify.
    Keep it short and friendly.
    
    User said: "{user_message}"
    """

    llm = get_llm_instance(1, config)
    response, usage = await invoke_llm_with_limit(1, llm, [HumanMessage(content=clarification_prompt)], config, max_tokens_override=settings.node_limits.clarification_agent, node_name="clarification_agent")

    logger.info(f"[Clarification] Low confidence intent — asking for clarification")

    return {
        "messages": [response],
        **update_token_usage(state, usage, node_name="clarification_agent")
    }
