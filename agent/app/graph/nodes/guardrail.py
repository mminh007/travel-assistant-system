# app/graph/nodes/guardrail.py
import hashlib
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

# Traffic split for A/B testing: 10% → model_b, 90% → model_a
_AB_TRAFFIC_SPLIT = 0.10
_AB_EXPERIMENT_NAME = "model_comparison_v1"


def _assign_ab_variant(session_id: str, traffic_split: float = _AB_TRAFFIC_SPLIT) -> str:
    """Deterministic A/B variant assignment based on session_id.

    Uses MD5 hashing to ensure the same session always maps to the same variant.
    This prevents users from seeing different model behaviors within the same session.

    Args:
        session_id: Unique session identifier (used as hash key)
        traffic_split: Fraction (0.0-1.0) of traffic routed to model_b. Default 10%.

    Returns:
        "model_b" if session is in treatment group, "model_a" otherwise.
    """
    hash_val = int(hashlib.md5(session_id.encode("utf-8")).hexdigest(), 16)
    return "model_b" if (hash_val % 100) < int(traffic_split * 100) else "model_a"


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

        # Assign A/B variant once per session — deterministic hashing ensures consistency
        session_id = state.get("session_id") or "unknown"
        ab_variant = _assign_ab_variant(session_id)
        logger.info(f"    A/B Variant: {ab_variant} (experiment={_AB_EXPERIMENT_NAME}, session={session_id[:8]}...)")

        if not decision.is_in_domain:
            COMPLEXITY_DISTRIBUTION.labels(complexity="low", intent_category="out_of_domain").inc()
            return {
                "is_in_domain": False,
                "intent_category": "out_of_domain",
                "complexity": "low",
                "objective": "Decline request politely",
                "detected_language": decision.detected_language,
                "model_variant": ab_variant,
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
            "model_variant": ab_variant,
            **update_token_usage(state, usage, node_name="input_guardrail")
        }
    except Exception as route_err:
        logger.error(f"❌ [GUARDRAIL FAILURE] Defaulting to travel framework -> Trace: {str(route_err)}")
        return {
            "is_in_domain": True,
            "intent_category": "travel_faq",
            "complexity": "low",
            "detected_language": "English",
            "model_variant": _assign_ab_variant(state.get("session_id") or "unknown"),
        }
