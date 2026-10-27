# app/graph/nodes/guardrail.py
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.runnables import RunnableConfig

from app.graph.state import AgentState
from app.graph.config import get_structured_llm, invoke_llm_with_limit
from app.graph.schemas import InputGuardrailOutput
from app.graph.utils import update_token_usage, load_agent_manifest_instructions
from app.core.settings import settings
from app.core.logger import setup_app_logger
from app.core.metrics import COMPLEXITY_DISTRIBUTION

logger = setup_app_logger("CognitiveNodes")


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
        ], config, max_tokens_override=settings.node_limits.input_guardrail, node_name="input_guardrail")
        logger.info(f"\n\n==> [PROCESS] INPUT_GUARDRAIL Initializing...")
        logger.info(f"    In Domain: [{decision.is_in_domain}] | Intent: {decision.intent_category.upper()} | Complexity: {decision.complexity.upper()}")
        logger.info(f"    Objective: {decision.objective}\n")

        if not decision.is_in_domain:
            COMPLEXITY_DISTRIBUTION.labels(complexity="low", intent_category="out_of_domain").inc()
            return {
                "is_in_domain": False,
                "intent_category": "out_of_domain",
                "complexity": "low",
                "objective": "Decline request politely",
                "detected_language": decision.detected_language,
                **update_token_usage(state, usage, node_name="input_guardrail")
            }

        COMPLEXITY_DISTRIBUTION.labels(
            complexity=decision.complexity or "medium",
            intent_category=decision.intent_category or "travel_faq",
        ).inc()
        return {
            "is_in_domain": decision.is_in_domain,
            "intent_category": decision.intent_category,
            "complexity": decision.complexity,
            "objective": decision.objective,
            "detected_language": decision.detected_language,
            "intent_confidence": decision.confidence,
            "ambiguity_reason": decision.ambiguity_reason,
            **update_token_usage(state, usage, node_name="input_guardrail")
        }
    except Exception as route_err:
        logger.error(f"❌ [GUARDRAIL FAILURE] Defaulting to travel framework -> Trace: {str(route_err)}")
        return {
            "is_in_domain": True,
            "intent_category": "travel_faq",
            "complexity": "low",
            "detected_language": "English"
        }
