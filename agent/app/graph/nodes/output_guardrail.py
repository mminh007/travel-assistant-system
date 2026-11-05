# app/graph/nodes/output_guardrail.py
"""
Node: OUTPUT_GUARDRAIL

Replaces the blocking evaluator_agent on the synchronous hot-path.
Runs lightweight validation after node_finding_extractor, before task_manager.

Strategy Pattern: switchable via GUARDRAIL_MODE environment variable.
  regex      (default) -- <5ms, no ML model, no GPU required.
                          Covers travel domain scope + basic safety.
  classifier (future)  -- 100-300ms, Guardrails AI + ML classifier.
                          Activate when GPU infrastructure is available.
                          Requires: pip install guardrails-ai guardrails-hub

Max 1 re-ask enforced (reask_count cap) -- NOT a rework loop.
"""
import re
from langchain_core.runnables import RunnableConfig

from app.graph.state import AgentState
from app.core.settings import settings
from app.core.logger import setup_app_logger

logger = setup_app_logger("OutputGuardrail")

# ───────────────────────────────────────────────────────────────
# Regex-based validator constants (GUARDRAIL_MODE=regex)
# ───────────────────────────────────────────────────────────────
_TRAVEL_KEYWORDS = re.compile(
    r"(hotel|kh\u00e1ch s\u1ea1n|flight|chuy\u1ebfn bay|itinerary|l\u1ecbch tr\u00ecnh|"
    r"travel|du l\u1ecbch|tour|resort|hostel|booking|\u0111\u1eb7t ph\u00f2ng|airfare|v\u00e9 m\u00e1y bay|"
    r"destination|\u0111i\u1ec3m \u0111\u1ebfn|check.?in|check.?out|visa|passport|luggage|accommodation)",
    re.IGNORECASE,
)
_TOXIC_PATTERNS = re.compile(
    r"\b(hack|exploit|jailbreak|ignore previous|bypass|rm -rf|drop table|<script)\b",
    re.IGNORECASE,
)
_MIN_RESPONSE_LENGTH = 50
_MAX_RESPONSE_LENGTH = 6000


def _validate_with_regex(raw_output: str) -> tuple[bool, str]:
    """
    Fast regex-based validation -- runs in <5ms, zero ML cost.
    Returns (passed, reason). reason is empty string on pass.
    """
    length = len(raw_output)
    if length < _MIN_RESPONSE_LENGTH:
        return False, f"Response too short ({length} chars, min={_MIN_RESPONSE_LENGTH})"
    if length > _MAX_RESPONSE_LENGTH:
        return False, f"Response too long ({length} chars, max={_MAX_RESPONSE_LENGTH})"
    if _TOXIC_PATTERNS.search(raw_output):
        return False, "Toxic or unsafe pattern detected in response"
    if not _TRAVEL_KEYWORDS.search(raw_output):
        return False, "Response does not appear to be travel-related"
    return True, ""


async def _validate_with_classifier(raw_output: str) -> tuple[bool, str]:
    """
    ML classifier-based validation using Guardrails AI.
    Activated via GUARDRAIL_MODE=classifier.
    Requires GPU infrastructure and guardrails-ai package.
    Latency: ~100-300ms.
    """
    try:
        from guardrails import Guard  # type: ignore
        from guardrails.hub import ToxicLanguage, ValidLength, RestrictToTopic  # type: ignore
        guard = Guard().use_many(
            RestrictToTopic(
                valid_topics=["travel", "hotel", "flight", "itinerary", "tourism", "booking"],
                on_fail="exception",
            ),
            ValidLength(min=_MIN_RESPONSE_LENGTH, max=_MAX_RESPONSE_LENGTH, on_fail="exception"),
            ToxicLanguage(threshold=0.5, on_fail="exception"),
        )
        guard.validate(raw_output)
        return True, ""
    except ImportError:
        logger.warning("[OutputGuardrail] guardrails-ai not installed. Falling back to regex mode.")
        return _validate_with_regex(raw_output)
    except Exception as e:
        return False, str(e)


async def node_output_guardrail(state: AgentState, config: RunnableConfig = None):
    """
    Node: OUTPUT_GUARDRAIL.
    Validates executor output before it reaches task_manager.
    On fail: triggers a single re-ask (reask_count=1 hard cap).
    On pass: routes to task_manager.
    """
    raw_output = state.get("raw_executor_output", "")
    reask_count = state.get("reask_count", 0)
    mode = getattr(settings, "guardrail_mode", "regex")

    # Hard cap: at most 1 re-ask. Prevents latency spiral.
    if reask_count >= 1:
        logger.warning("[OutputGuardrail] Re-ask limit reached (count=%d) -- passing through.", reask_count)
        return {"guardrail_passed": True}

    if mode == "classifier":
        passed, reason = await _validate_with_classifier(raw_output)
    else:
        passed, reason = _validate_with_regex(raw_output)

    if passed:
        logger.info("[OutputGuardrail] PASS (mode=%s, len=%d)", mode, len(raw_output))
    else:
        logger.warning("[OutputGuardrail] FAIL (mode=%s): %s. Triggering re-ask.", mode, reason)

    return {
        "guardrail_passed": passed,
        "reask_count": reask_count + (0 if passed else 1),
    }


def route_from_output_guardrail(state: AgentState) -> str:
    """Routes to travel_react_agent for re-ask, or to task_manager on pass."""
    return "pass" if state.get("guardrail_passed", True) else "reask"
