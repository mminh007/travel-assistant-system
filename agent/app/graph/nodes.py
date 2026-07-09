# app/graph/nodes.py
import os
import functools
import tiktoken
from typing import Dict, Any, List, Literal, Optional
from pydantic import BaseModel, Field
import json

from langchain_core.messages import SystemMessage, HumanMessage, RemoveMessage, AIMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.language_models.chat_models import BaseChatModel

from app.graph.state import AgentState
from app.services.query_transformer import transform_user_query
from app.mcp.tool_registry import get_tools_by_domain
from app.core.settings import settings
from app.core.logger import setup_app_logger
from app.core.metrics import GRAPH_ITERATIONS
from app.bootstrap.container import container
from app.graph.config import get_cached_bound_llm, get_structured_llm, get_llm_instance, invoke_llm_with_limit

logger = setup_app_logger("CognitiveNodes")

FINDING_CONFIDENCE_THRESHOLD = 0.5


# ─── STRUCTURED OUTPUT SCHEMAS ───

class InputGuardrailOutput(BaseModel):
    is_in_domain: bool = Field(description="True if the request is related to travel, flights, hotels, or travel FAQs. False otherwise.")
    intent_category: Literal["hotel_booking", "travel_faq", "itinerary_planning", "system_navigation_faq", "out_of_domain", "ambiguous"] = Field(description="The category of the user's request.")
    complexity: str = Field(description="Level of complexity: 'low', 'medium', 'high'.")
    objective: str = Field(description="The overarching execution objective for the Planner.")
    detected_language: str = Field(description="The detected language of the user's prompt (e.g., 'English', 'Vietnamese', 'Spanish').")
    rationale: str = Field(description="Internal chain-of-thought justification.")
    confidence: float = Field(default=1.0, description="Confidence score 0.0-1.0 for the intent classification.")
    ambiguity_reason: Optional[str] = Field(default=None, description="If confidence < 0.7, explain what is ambiguous.")

def update_token_usage(state: AgentState, usage) -> dict:
    cost_in = usage.input_tokens * (0.15 if usage.tier == 1 else 5.0) / 1000000
    cost_out = usage.output_tokens * (0.60 if usage.tier == 1 else 15.0) / 1000000
    cost = cost_in + cost_out
    tier_prefix = f"tier{usage.tier}"
    in_key = f"{tier_prefix}_input_tokens"
    out_key = f"{tier_prefix}_output_tokens"
    return {
        in_key: (state.get(in_key) or 0) + usage.input_tokens,
        out_key: (state.get(out_key) or 0) + usage.output_tokens,
        "estimated_cost_usd": (state.get("estimated_cost_usd") or 0.0) + cost
    }

class TaskItem(BaseModel):
    id: int = Field(description="Unique incremental ID for the task.")
    description: str = Field(description="Clear, actionable description of the sub-task.")

class PlannerOutput(BaseModel):
    tasks: List[TaskItem] = Field(description="List of sequential tasks required to fulfill the user's travel request.")

class Finding(BaseModel):
    statement: str = Field(description="A concise factual statement.")
    evidence: Optional[str] = Field(default=None, description="Evidence or citation supporting this statement.")
    confidence: float = Field(description="Confidence level in this finding (0.0 to 1.0).")

class ExecutorOutput(BaseModel):
    """
    Schema used exclusively by node_finding_extractor (not by executor nodes directly).
    Executor nodes now produce free-form Markdown; this schema is applied in a
    dedicated downstream extraction step to avoid JSON formatting failures.
    """
    result_summary: str = Field(description="A concise 1-3 sentence summary of the main answer or result.")
    findings: List[Finding] = Field(description="Key factual findings extracted from the executor's response.")

class EvaluatorOutput(BaseModel):
    objective_met: bool = Field(description="Assess if the executor fully achieved the initial objective.")
    tool_quality_score: int = Field(description="Score (1-10) evaluating the appropriate use of tools and context.")
    evidence_quality_score: int = Field(description="Score (1-10) evaluating the strength of evidence supporting the findings.")
    citation_quality_score: int = Field(description="Score (1-10) evaluating proper source citations.")
    freshness_score: int = Field(description="Score (1-10) evaluating the recency/freshness of the information.")
    feedback: str = Field(description="Detailed feedback synthesizing the evaluations into a final verdict.")
    needs_rework: bool = Field(description="Determine if the executor needs to rerun based on the critic's severity.")
    actionable_advice: str = Field(description="Strict, actionable instructions for the executor or synthesis notes if passing.")

class FactCheckResult(BaseModel):
    is_consistent: bool = Field(description="True if the extracted findings are fully consistent with the raw tool observations. False if there are contradictions.")
    consistency_score: float = Field(description="0.0 = completely contradictory, 1.0 = completely consistent")
    contradictions: List[str] = Field(description="List of factual contradictions discovered, if any.")
    ungrounded_claims: List[str] = Field(description="List of claims that are not grounded in the tool observations.")


# ─── UTILITY FUNCTIONS ───

def prune_messages_by_token_limit(messages: list, max_tokens: int, model_name: str) -> list:
    """Ensures message history strictly respects context window boundaries."""
    try:
        encoding = tiktoken.encoding_for_model(model_name)
    except KeyError:
        encoding = tiktoken.get_encoding("o200k_base")

    total_tokens = 0
    keep_messages = []
    for msg in reversed(messages):
        msg_tokens = len(encoding.encode(msg.content))
        if total_tokens + msg_tokens > max_tokens:
            break
        keep_messages.insert(0, msg)
        total_tokens += msg_tokens
    return keep_messages


def _build_task_context(state: AgentState) -> str:
    """
    Builds a plain-text task context block for injection into executor system prompts.

    REPLACES: _build_executor_instructions() which previously appended JSON formatting
    directives alongside task context — the root cause of JSONDecodeError failures
    when executors generated Markdown or code snippet responses.

    Executors now receive ONLY task context; JSON formatting is never requested here.
    Structured extraction is performed downstream by node_finding_extractor.
    """
    tasks = state.get("tasks", [])
    current_task_id = state.get("current_task_id")

    completed_findings = []
    for t in tasks:
        if t.get("status") == "completed" and t.get("findings"):
            for f in t["findings"]:
                confidence = f.get("confidence", 0.0) if isinstance(f, dict) else getattr(f, "confidence", 0.0)
                stmt = f.get("statement", "") if isinstance(f, dict) else getattr(f, "statement", "")
                completed_findings.append(f"  - Task {t['id']}: {stmt} (confidence: {confidence:.2f})")

    active_task = next((t for t in tasks if t["id"] == current_task_id), None) if current_task_id else None

    parts = []
    if active_task:
        parts.append(f"CURRENT ACTIVE TASK: {active_task['desc']}")
    if completed_findings:
        parts.append("PRIOR TASK FINDINGS (for context):\n" + "\n".join(completed_findings))

    return "\n\n".join(parts) if parts else ""


@functools.lru_cache(maxsize=1)
def load_agent_manifest_instructions(file_path: str = "workflow.md") -> str:
    """
    Extracts baseline operational principles from the external Markdown manifest.
    Cached after first read — manifest is static for the lifetime of the process.
    """
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            logger.info("==> [Manifest] Loaded workflow.md into cache.")
            return f.read()
    return "You are a highly capable engineering AI assistant."


# ─── GRAPH NODES ───

async def node_input_guardrail(state: AgentState, config: RunnableConfig = None):
    """
    Node 0: Input Guardrail. Classifies intent and checks if in domain.
    """
    user_latest_message = state["messages"][-1].content
    manifest = load_agent_manifest_instructions()

    try:
        structured_llm = get_structured_llm(1, InputGuardrailOutput, config)
        decision, usage = await invoke_llm_with_limit(1, structured_llm, [
            SystemMessage(content=f"{manifest}\n\nAnalyze the current human message. Is it a travel booking/faq request, or a question about how to use the website (system_navigation_faq)?"),
            HumanMessage(content=user_latest_message)
        ], config)
        logger.info(f"\n\n==> [PROCESS] INPUT_GUARDRAIL Initializing...")
        logger.info(f"    In Domain: [{decision.is_in_domain}] | Intent: {decision.intent_category.upper()} | Complexity: {decision.complexity.upper()}")
        logger.info(f"    Objective: {decision.objective}\n")

        if not decision.is_in_domain:
            return {
                "is_in_domain": False,
                "intent_category": "out_of_domain",
                "complexity": "low",
                "objective": "Decline request politely",
                "detected_language": decision.detected_language,
                **update_token_usage(state, usage)
            }

        return {
            "is_in_domain": decision.is_in_domain,
            "intent_category": decision.intent_category,
            "complexity": decision.complexity,
            "objective": decision.objective,
            "detected_language": decision.detected_language,
            "intent_confidence": decision.confidence,
            "ambiguity_reason": decision.ambiguity_reason,
            **update_token_usage(state, usage)
        }
    except Exception as route_err:
        logger.error(f"❌ [GUARDRAIL FAILURE] Defaulting to travel framework -> Trace: {str(route_err)}")
        return {
            "is_in_domain": True,
            "intent_category": "travel_faq",
            "complexity": "low",
            "detected_language": "English"
        }

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

    llm = get_llm_instance(config)
    
    # Optional: Bind ONLY the specific tool (like vector search) if we had the tool registry ready here. 
    # For now, we bind the mcp tools that allow Qdrant read (we assume travel_react_agent tools are shared or mcp tools include qdrant search).
    from app.mcp.mcp_client import get_mcp_tools
    mcp_tools = get_mcp_tools()
    # In a real isolation, we would filter mcp_tools to ONLY include qdrant_search, excluding tavily_search.
    safe_tools = [t for t in mcp_tools if "search_tavily" not in t.name]
    bound_llm = llm.bind_tools(safe_tools)

    response = await bound_llm.ainvoke([
        SystemMessage(content=support_system_prompt),
        HumanMessage(content=user_latest_message)
    ], config)

    # Convert ToolMessage handling or just return AIMessage if it directly responds
    return {"messages": [response]}



async def node_planner_agent(state: AgentState, config: RunnableConfig = None):
    """
    Node: PLANNER_AGENT.
    Acts as the project manager. Takes a complex travel query, evaluates feasibility,
    and breaks it down into a linear execution plan stored in Workflow Memory.
    """
    user_initial_prompt = state["messages"][-1].content if state["messages"] else ""
    objective = state.get("objective", user_initial_prompt)
    logger.info(f"==> [Planner] Breaking down travel request: '{user_initial_prompt[:50]}...'")

    try:
        structured_planner_llm = get_structured_llm(2, PlannerOutput, config)
        plan, usage = await invoke_llm_with_limit(2, structured_planner_llm, [
            SystemMessage(
                content=(
                    "You are the Travel Master Planner. Break down the user's travel request into 2-4 "
                    "concrete, sequential sub-tasks. Focus on logical progression.\n\n"
                    f"Overarching Objective: {objective}\n"
                    "CRITICAL ROUTING RULES:\n"
                    "- Only output logical travel tasks like 'Search for hotel', 'Check availability', etc."
                )
            ),
            HumanMessage(content=user_initial_prompt)
        ], config)

        tasks_state = [
            {"id": t.id, "desc": t.description, "status": "pending", "result": None, "findings": []}
            for t in plan.tasks
        ]
        logger.info(f"==> [Planner] Generated {len(tasks_state)} tasks successfully.")
        token_update = update_token_usage(state, usage)

    except Exception as plan_err:
        logger.error(f"❌ [PLANNER FAILURE] Structured parse failed — falling back to single task. Trace: {str(plan_err)}")
        tasks_state = [{"id": 1, "desc": user_initial_prompt, "status": "pending", "result": None, "findings": []}]
        token_update = {}

    return {
        "tasks": tasks_state,
        "current_task_id": tasks_state[0]["id"] if tasks_state else None,
        "iteration_count": 0,
        "tool_call_count": 0,
        "action_history": [],
        "rework_count": 0,
        **token_update
    }


async def node_travel_react_agent(state: AgentState, config: RunnableConfig = None):
    """
    Node: TRAVEL_REACT_AGENT.
    Operating as a true topological ReAct Agent specifically for Travel tasks.
    """
    user_id = state.get("user_id", "UNKNOWN_USER")
    intent_category = state.get("intent_category", "travel_faq")

    if not container.hybrid_search:
        await container.initialize()

    user_initial_prompt = state["messages"][0].content if state["messages"] else ""
    manifest = load_agent_manifest_instructions()
    task_context = _build_task_context(state)

    intent_category = state.get("intent_category", "travel_faq")

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

    base_llm = get_llm_instance(2, config)
    llm_with_tools = get_cached_bound_llm("travel", base_llm)

    from app.graph.config import _resolve_provider_and_key
    provider, provider_cfg, _ = _resolve_provider_and_key(config)
    
    compiled_messages = prune_messages_by_token_limit(
        compiled_messages,
        provider_cfg.max_context_tokens,
        provider_cfg.tier2_balanced_model
    )

    current_iteration = state.get("iteration_count", 0) + 1

    response, usage = await invoke_llm_with_limit(2, llm_with_tools, compiled_messages, config)
    return {
        "messages": [response],
        "iteration_count": current_iteration,
        **update_token_usage(state, usage)
    }


async def node_finding_extractor(state: AgentState, config: RunnableConfig = None):
    """
    Node: FINDING_EXTRACTOR.

    PURPOSE — Separation of Content Generation from Information Extraction:
    Executor nodes (travel_react_agent) now
    produce free-form Markdown responses. This node reads that plain text and applies
    a dedicated, low-cost Tier-1 structured-output call to extract:
      - result_summary: a concise 1-3 sentence digest of the executor's answer
      - findings: a typed List[Finding] with statements, evidence, and confidence scores

    WHY THIS DESIGN:
    Previously, executors were prompted to output the entire answer inside a JSON string
    field (result: str). Code snippets, markdown headers, and unescaped quotes in that
    field caused frequent JSONDecodeError failures. By separating generation from
    extraction, executors can produce any format naturally; extraction is handled here
    where a short, well-scoped prompt reliably produces valid JSON via Function Calling.

    RESULT: Writes to state['raw_executor_output'] and state['extracted_findings'],
    which are consumed by node_task_manager (no JSON parsing from messages needed).
    """
    logger.info("==> [PROCESS] FINDING_EXTRACTOR Extracting structured findings from executor output...")

    executor_raw = state["messages"][-1].content

    extraction_prompt = (
        "You are a precise Information Extraction engine. Your ONLY job is to read the "
        "following executor response and extract structured data.\n\n"
        "Extract:\n"
        "1. result_summary — a concise 1-3 sentence digest capturing the main answer or conclusion.\n"
        "2. findings — a list of key factual claims, each with:\n"
        "   - statement: a single, self-contained factual sentence\n"
        "   - evidence: a quote or citation from the text (optional)\n"
        "   - confidence: a float from 0.0 (uncertain) to 1.0 (certain)\n\n"
        f"<executor_output>\n{executor_raw}\n</executor_output>"
    )

    try:
        # Tier 1 (fast/cheap model) is sufficient — extraction is a short, focused call
        structured_extractor = get_structured_llm(1, ExecutorOutput, config)
        extraction, usage = await invoke_llm_with_limit(1, structured_extractor, [
            HumanMessage(content=extraction_prompt)
        ], config)
        raw_summary = extraction.result_summary
        findings = [f.model_dump() for f in extraction.findings]
        logger.info(f"    Extracted {len(findings)} finding(s). Summary: '{raw_summary[:80]}...'")
        token_update = update_token_usage(state, usage)
    except Exception as e:
        logger.error(f"❌ [EXTRACTOR FAILURE] Falling back to raw executor text. Trace: {str(e)}")
        raw_summary = executor_raw
        findings = []
        token_update = {}

    return {
        "raw_executor_output": raw_summary,
        "extracted_findings": findings,
        **token_update
    }


async def node_fact_checker(state: AgentState, config: RunnableConfig = None):
    """
    Node: FACT_CHECKER.
    Compares extracted_findings with raw tool observations to detect hallucinations.
    """
    logger.info("==> [PROCESS] FACT_CHECKER Verifying factual consistency...")
    
    tool_observations = [
        msg.content for msg in state["messages"]
        if getattr(msg, "type", "") == "tool"
    ]
    
    extracted_findings = state.get("extracted_findings", [])
    
    if not tool_observations:
        logger.info("    No tool observations found. Skipping fact check.")
        return {
            "fact_check_result": {"is_consistent": True, "contradictions": [], "consistency_score": 1.0, "ungrounded_claims": []}
        }
        
    check_prompt = f"""
    You are a Fact Verification engine.
    
    TOOL RESULTS (Ground Truth):
    {json.dumps(tool_observations, ensure_ascii=False)}
    
    EXECUTOR CLAIMS (to verify):
    {json.dumps(extracted_findings, ensure_ascii=False)}
    
    Task: Find any contradictions between executor claims and tool results.
    Focus on: prices, dates, names, quantities, availability status.
    """
    
    try:
        structured_checker = get_structured_llm(1, FactCheckResult, config)
        result, usage = await invoke_llm_with_limit(1, structured_checker, [HumanMessage(content=check_prompt)], config)
        
        if not result.is_consistent:
            logger.warning(f"⚠️ [FACT CHECK] Contradictions detected: {result.contradictions}")
            
        token_update = update_token_usage(state, usage)
        
        feedback = f"[Fact Check] Consistency: {result.consistency_score:.2f}. {'; '.join(result.contradictions)}" if result.contradictions else ""
        
        return {
            "fact_check_result": result.model_dump(),
            "evaluator_feedback": feedback,
            **token_update
        }
    except Exception as e:
        logger.error(f"❌ [FACT CHECK FAILURE] Skipping validation. Trace: {str(e)}")
        return {}


async def node_direct_executor_init(state: AgentState):
    """
    Node: DIRECT_EXECUTOR_INIT.
    Lightweight initializer for the complexity='low' bypass path.
    Skips Planner to save LLM cost, creates a single synthetic task from the user prompt,
    and sets all required loop counters to their initial values.
    """
    user_initial_prompt = state["messages"][-1].content if state["messages"] else ""
    objective = state.get("objective", user_initial_prompt)
    tasks_state = [{"id": 1, "desc": objective, "status": "pending", "result": None, "findings": []}]

    logger.info("==> [DirectInit] Low-complexity bypass: skipping Planner, single task created.")

    return {
        "tasks": tasks_state,
        "current_task_id": 1,
        "iteration_count": 0,
        "tool_call_count": 0,
        "action_history": [],
        "rework_count": 0
    }


# ─── EVALUATION NODES ───

async def node_evaluator_agent(state: AgentState, config: RunnableConfig = None):
    """
    Node: EVALUATOR_AGENT. Replaces both critic_agent and reflection_agent.
    Evaluates executor output against the overarching objective and decides if rework is needed.
    """
    logger.info(f"\n\n==> [PROCESS] EVALUATOR_AGENT Auditing execution trajectory...")

    objective = state.get("objective", "Provide a comprehensive answer.")
    executor_payload = state.get("raw_executor_output") or state["messages"][-1].content
    findings = state.get("extracted_findings", [])
    action_history = state.get("action_history", [])
    current_rework_count = state.get("rework_count", 0)

    evaluation_prompt = (
        f"You are the EVALUATOR_AGENT.\n"
        f"MASTER OBJECTIVE: {objective}\n\n"
        f"Critically analyze if the Executor fulfilled the objective.\n"
        f"Provide integer scores (1-10) for tool_quality_score, evidence_quality_score, "
        f"citation_quality_score, and freshness_score.\n"
        f"Expose missing data or hallucinated parameters in your feedback.\n"
        f"Determine if rework is absolutely required. If yes, generate strict actionable instructions. "
        f"If no, draft a synthesis memo.\n\n"
        f"<executor_payload>\n{executor_payload}\n</executor_payload>\n\n"
        f"<extracted_findings>\n{findings}\n</extracted_findings>\n\n"
        f"<action_history>\n{action_history}\n</action_history>"
    )

    try:
        structured_evaluator_llm = get_structured_llm(2, EvaluatorOutput, config)
        evaluation, usage = await invoke_llm_with_limit(2, structured_evaluator_llm, [HumanMessage(content=evaluation_prompt)], config)
        token_update = update_token_usage(state, usage)
    except Exception as e:
        logger.error(f"❌ [EVALUATOR FAILURE] Parse error: {str(e)}")
        evaluation = EvaluatorOutput(
            objective_met=True,
            tool_quality_score=5, evidence_quality_score=5, citation_quality_score=5, freshness_score=5,
            feedback="[Fallback] Parsing failed, proceeding automatically.",
            needs_rework=False, actionable_advice="[Fallback] Proceeding without rework."
        )
        token_update = {}

    new_rework_count = current_rework_count + 1 if evaluation.needs_rework else current_rework_count

    logger.info(f"    Status: {'✅ MET' if evaluation.objective_met else '❌ DEFICIENT'}")
    logger.info(f"    Scores: Tools={evaluation.tool_quality_score}, Evidence={evaluation.evidence_quality_score}, "
                f"Citations={evaluation.citation_quality_score}, Freshness={evaluation.freshness_score}")
    logger.info(f"    Correction Required: {evaluation.needs_rework} | Rework Cycle: {new_rework_count}")
    logger.info(f"    Directive: {evaluation.actionable_advice}\n")

    return {
        "evaluator_feedback": evaluation.feedback,
        "evaluator_notes": evaluation.actionable_advice,
        "needs_rework": evaluation.needs_rework,
        "rework_count": new_rework_count,
        **token_update
    }


async def node_final_synthesizer(state: AgentState, config: RunnableConfig = None):
    """
    Node: FINAL_SYNTHESIZER. Compiles the ultimate formatted response.
    Reads from completed task results and findings to produce a polished Markdown answer.
    """
    logger.info(f"\n\n==> [PROCESS] FINAL_SYNTHESIZER Constructing final payload...")

    current_objective = state.get("objective", state["messages"][-1].content if state["messages"] else "")
    detected_language = state.get("detected_language", "English")
    tasks = state.get("tasks", [])

    all_findings = []
    all_results = []
    for t in tasks:
        if t.get("findings"):
            for f in t["findings"]:
                stmt = f.get("statement", "") if isinstance(f, dict) else getattr(f, "statement", "")
                confidence = f.get("confidence", 1.0) if isinstance(f, dict) else getattr(f, "confidence", 1.0)
                if confidence < FINDING_CONFIDENCE_THRESHOLD:
                    stmt = f"{stmt} (⚠️ Unverified / Low Confidence)"
                all_findings.append(f"- {stmt}")
        if t.get("result"):
            all_results.append(f"### Task: {t['desc']}\n{t['result']}")

    findings_text = "\n".join(all_findings) if all_findings else "No key findings extracted."
    results_text = "\n\n".join(all_results) if all_results else "No detailed results available."

    synthesis_prompt = (
        "You are the FINAL_SYNTHESIZER. Create a highly polished, professional Markdown response "
        "that directly addresses the user's request.\n"
        f"CRITICAL RULE: You MUST output your final response entirely in the following language: {detected_language}\n"
        "CRITICAL: Do NOT wrap the final response in a markdown code block (e.g. do not wrap the response with ```markdown or ```). Output plain Markdown text directly.\n"
        "Synthesize the outputs from the completed tasks into a coherent and unified answer. "
        "Do not artificially separate the response into 'Key Findings' and 'Detailed Analysis' unless appropriate.\n"
        "Extract, deduplicate, and compile any sources/citations into a 'Bibliography' at the end if applicable.\n\n"
        f"<user_objective>\n{current_objective}\n</user_objective>\n\n"
        f"<task_findings>\n{findings_text}\n</task_findings>\n\n"
        f"<task_results>\n{results_text}\n</task_results>\n"
    )

    final_response, usage = await invoke_llm_with_limit(2, get_llm_instance(2, config), [HumanMessage(content=synthesis_prompt)], config)

    # Clean any leading/trailing markdown code fences as a failsafe
    if final_response and hasattr(final_response, "content") and isinstance(final_response.content, str):
        content = final_response.content.strip()
        if content.startswith("```markdown") and content.endswith("```"):
            content = content[11:-3].strip()
        elif content.startswith("```") and content.endswith("```"):
            content = content[3:-3].strip()
        final_response.content = content
        
    total_iterations = state.get("iteration_count", 0)
    GRAPH_ITERATIONS.labels(domain=state.get("current_domain", "general_memory")).observe(total_iterations)

    logger.info("    Process Complete. Handshake ready.\n\n")

    return {
        "messages": [final_response],
        **update_token_usage(state, usage)
    }


async def node_task_manager(state: AgentState):
    """
    Node: TASK_MANAGER.
    Manages iterating through Planner tasks. Marks current as complete, advances pointer.

    REFACTORED: No longer performs JSON parsing from executor message content.
    Instead reads directly from state['raw_executor_output'] and state['extracted_findings'],
    which are set by node_finding_extractor. This eliminates the fragile try/except
    JSON parse that previously lost findings on any formatting error.
    """
    logger.info(f"\n\n==> [PROCESS] TASK_MANAGER Auditing task registry...")

    tasks = state.get("tasks", [])
    current_task_id = state.get("current_task_id")

    if not tasks:
        logger.info("    No tasks registered. Proceeding.")
        return {"current_task_id": None}

    # Read structured data directly from state — set by node_finding_extractor
    extracted_result = state.get("raw_executor_output") or state["messages"][-1].content
    extracted_findings = state.get("extracted_findings", [])

    updated_tasks = []
    for t in tasks:
        if t["id"] == current_task_id:
            t["status"] = "completed"
            t["result"] = extracted_result
            t["findings"] = extracted_findings
        updated_tasks.append(t)

    next_task = next((t for t in updated_tasks if t.get("status") == "pending"), None)

    if next_task:
        logger.info(f"    Advancing to Next Task -> [{next_task['id']}]: {next_task['desc']}")
        # Context Sandboxing: clear execution messages generated during this task, 
        # keeping the conversation history up to the latest user prompt
        last_human_idx = len(state["messages"]) - 1
        for i in range(len(state["messages"]) - 1, -1, -1):
            if getattr(state["messages"][i], "type", "") == "human" or isinstance(state["messages"][i], HumanMessage):
                last_human_idx = i
                break
                
        messages_to_remove = [RemoveMessage(id=m.id) for m in state["messages"][last_human_idx+1:] if getattr(m, "id", None)]

        return {
            "tasks": updated_tasks,
            "current_task_id": next_task["id"],
            "iteration_count": 0,
            "tool_call_count": 0,
            "rework_count": 0,
            # Reset extraction state for the next task cycle
            "raw_executor_output": None,
            "extracted_findings": [],
            "messages": messages_to_remove
        }
    else:
        logger.info("    All tasks completed. Proceeding to synthesis.")
        return {
            "tasks": updated_tasks,
            "current_task_id": None
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
    response, usage = await invoke_llm_with_limit(1, llm, [HumanMessage(content=clarification_prompt)], config)
    
    logger.info(f"[Clarification] Low confidence intent — asking for clarification")
    
    return {
        "messages": [response],
        **update_token_usage(state, usage)
    }
