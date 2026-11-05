# app/graph/nodes/evaluator.py
import json
import re
from datetime import date
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

from app.graph.state import AgentState
from app.graph.config import get_structured_llm, invoke_llm_with_limit
from app.graph.schemas import EvaluatorOutput, FactCheckResult
from app.graph.utils import update_token_usage
from app.core.settings import settings
from app.core.logger import setup_app_logger

logger = setup_app_logger("CognitiveNodes")

_MAX_EVAL_PAYLOAD_CHARS = 4000
_MAX_FC_OBSERVATION_CHARS = 4000

# ─── Fix A: Fallback template on forced_accept=True ───
# Instead of returning the raw deficient response to the user, wrap it in a safe disclaimer.
_FORCED_ACCEPT_FALLBACK_TEMPLATE = (
    "I attempted to gather information for your request, "
    "but could not fully verify its accuracy after multiple review cycles.\n"
    "Below is the best-effort result — please verify before making any decisions:\n\n"
    "{best_effort_content}"
)

# ─── Fix B: Hardcoded scoring rubric for the evaluator ───
# Replaces subjective scoring with explicit anchor definitions → scores are consistent
# across runs and immediately usable as a baseline for Langfuse trend analysis.
_SCORING_RUBRIC = """
SCORING RUBRIC — Use these exact definitions, NOT personal intuition:

tool_quality_score (1-10):
  10 = All needed tools called; results complete and directly relevant
   7 = Most tools called; minor gaps in returned data
   4 = Missing key tool calls; significant data gaps
   1 = No relevant tools called at all

evidence_quality_score (1-10):
  10 = Every claim backed by a concrete tool observation (price/date/name cited)
   7 = Most claims backed; minor unsupported assertions present
   4 = Many claims ungrounded or vague
   1 = Pure hallucination; no tool evidence used

citation_quality_score (1-10):
  10 = Sources explicitly named for all facts (hotel name, URL, tool ID)
   7 = Sources named for key facts; minor gaps
   4 = Sources rarely mentioned
   1 = No citations at all

freshness_score (1-10):
  10 = All data retrieved live from tools in this exact session
   7 = Mix of live tool data and known/cached facts
   4 = Mostly parametric memory; few live tool calls made
   1 = Entirely from parametric memory; no retrieval performed
"""


# ─── Fix C: Deterministic pre-checks (Tier 1 — <1ms, zero LLM cost) ───
def _run_deterministic_checks(findings: list) -> list[str]:
    """
    Fast rule-based checks that run before the LLM fact-checker call.
    Catches obvious violations: negative/zero prices, invalid dates, past dates in a booking context.
    Returns a list of violation strings — empty list means all checks passed.
    """
    violations = []
    today = date.today()

    for f in findings:
        content = f.get("content", "") if isinstance(f, dict) else str(f)

        # Check 1: Negative or zero price
        prices = re.findall(r'([\d][\d,\.]+)\s*(?:VND|USD|đ|\$|vnđ)', content, re.IGNORECASE)
        for price_str in prices:
            try:
                price_val = float(price_str.replace(",", "").replace(".", ""))
                if price_val <= 0:
                    violations.append(f"Invalid price <= 0: '{price_str}'")
            except ValueError:
                pass

        # Check 2: Past dates in a booking context (formats: dd/mm/yyyy or dd-mm-yyyy)
        date_matches = re.findall(r'\b(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})\b', content)
        for d, m, y in date_matches:
            try:
                parsed_date = date(int(y), int(m), int(d))
                if parsed_date < today:
                    violations.append(f"Past date found (may be invalid for booking): {d}/{m}/{y}")
            except ValueError:
                violations.append(f"Invalid date format detected: {d}/{m}/{y}")

    return violations


async def node_fact_checker(state: AgentState, config: RunnableConfig = None):
    """
    Node: FACT_CHECKER.
    Compares extracted_findings with raw tool observations to detect hallucinations.

    Pipeline:
      [Fix C] Tier 1 — Deterministic checks (<1ms, zero LLM cost)
              ↓
              Tier 4 — LLM consistency check (Tier-1 LLM, runs after Tier 1 passes)
    """
    logger.info("==> [PROCESS] FACT_CHECKER Verifying factual consistency...")

    tool_observations = [
        msg.content for msg in state["messages"]
        if getattr(msg, "type", "") == "tool"
    ]

    extracted_findings = state.get("extracted_findings", [])

    # ─── Fix C: Tier 1 — Deterministic pre-checks ───
    # Runs before the LLM call to catch obvious violations (negative price, invalid date).
    deterministic_issues = _run_deterministic_checks(extracted_findings)
    if deterministic_issues:
        logger.warning(f"⚠️ [DETERMINISTIC CHECK] {len(deterministic_issues)} issue(s) found: {deterministic_issues}")
    else:
        logger.info("    [DETERMINISTIC CHECK] Passed — no obvious price/date violations.")

    if not tool_observations:
        logger.info("    No tool observations found. consistency_score=None (unverifiable, not 1.0).")
        # Still surface deterministic issues even when there is no tool data to compare against
        det_feedback = f"[Deterministic] Issues: {'; '.join(deterministic_issues)}" if deterministic_issues else ""
        return {
            "fact_check_result": {
                "is_consistent": None,
                "contradictions": deterministic_issues,
                "consistency_score": None,
                "ungrounded_claims": [],
                "verification_status": "no_tool_data"
            },
            "fact_check_feedback": det_feedback,
        }

    raw_obs_str = json.dumps(tool_observations, ensure_ascii=False)
    if len(raw_obs_str) > _MAX_FC_OBSERVATION_CHARS:
        raw_obs_str = raw_obs_str[:_MAX_FC_OBSERVATION_CHARS] + " ...[TRUNCATED]"

    check_prompt = f"""
    You are a Fact Verification engine.

    TOOL RESULTS (Ground Truth):
    {raw_obs_str}

    EXECUTOR CLAIMS (to verify):
    {json.dumps(extracted_findings, ensure_ascii=False)}

    Task: Find any contradictions between executor claims and tool results.
    Focus on: prices, dates, names, quantities, availability status.
    """

    try:
        structured_checker = get_structured_llm(1, FactCheckResult, config)
        result, usage = await invoke_llm_with_limit(
            1, structured_checker, [HumanMessage(content=check_prompt)],
            config, max_tokens_override=settings.node_limits.fact_checker, node_name="fact_checker"
        )

        if not result.is_consistent:
            logger.warning(f"⚠️ [FACT CHECK] Contradictions detected: {result.contradictions}")

        token_update = update_token_usage(state, usage, node_name="fact_checker")

        # Merge deterministic issues + LLM-detected contradictions into the final feedback string
        all_issues = deterministic_issues + (result.contradictions or [])
        feedback = (
            f"[Fact Check] Consistency: {result.consistency_score:.2f}. {'; '.join(all_issues)}"
            if all_issues else ""
        )

        return {
            "fact_check_result": result.model_dump(),
            "fact_check_feedback": feedback,  # Dedicated field — does NOT overwrite evaluator_feedback
            **token_update
        }
    except Exception as e:
        logger.error(f"❌ [FACT CHECK FAILURE] Skipping validation. Trace: {str(e)}")
        return {}


async def node_evaluator_agent(state: AgentState, config: RunnableConfig = None):
    """
    Node: EVALUATOR_AGENT. Replaces both critic_agent and reflection_agent.
    Evaluates executor output against the overarching objective and decides if rework is needed.
    """
    logger.info(f"\n\n==> [PROCESS] EVALUATOR_AGENT Auditing execution trajectory...")

    objective = state.get("objective", "Provide a comprehensive answer.")
    executor_payload = state.get("raw_executor_output") or state["messages"][-1].content
    if isinstance(executor_payload, str) and len(executor_payload) > _MAX_EVAL_PAYLOAD_CHARS:
        executor_payload = executor_payload[:_MAX_EVAL_PAYLOAD_CHARS] + " ...[TRUNCATED]"

    findings = state.get("extracted_findings", [])
    action_history = state.get("action_history", [])
    current_rework_count = state.get("rework_count", 0)

    # ─── Fix B: Inject scoring rubric into the prompt ───
    # Replaces intuition-based scoring with explicit 1/4/7/10 anchor definitions,
    # producing consistent scores across runs and a reliable baseline for Langfuse.
    evaluation_prompt = (
        f"You are the EVALUATOR_AGENT.\n"
        f"{_SCORING_RUBRIC}\n"
        f"MASTER OBJECTIVE: {objective}\n\n"
        f"Critically analyze if the Executor fulfilled the objective.\n"
        f"Provide integer scores (1-10) strictly following the SCORING RUBRIC above "
        f"for tool_quality_score, evidence_quality_score, citation_quality_score, and freshness_score.\n"
        f"Expose missing data or hallucinated parameters in your feedback.\n"
        f"Determine if rework is absolutely required. If yes, generate strict actionable instructions. "
        f"If no, draft a synthesis memo.\n\n"
        f"<executor_payload>\n{executor_payload}\n</executor_payload>\n\n"
        f"<extracted_findings>\n{findings}\n</extracted_findings>\n\n"
        f"<action_history>\n{action_history}\n</action_history>"
    )

    try:
        structured_evaluator_llm = get_structured_llm(2, EvaluatorOutput, config)
        evaluation, usage = await invoke_llm_with_limit(2, structured_evaluator_llm, [HumanMessage(content=evaluation_prompt)], config, max_tokens_override=settings.node_limits.evaluator_agent, node_name="evaluator_agent")
        token_update = update_token_usage(state, usage, node_name="evaluator_agent")
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
    max_rework = getattr(settings, "max_rework_cycles", 2)
    rework_limit_reached = new_rework_count >= max_rework

    effective_needs_rework = evaluation.needs_rework
    _forced_accept = False  # Set True if rework limit reached with deficient response
    if effective_needs_rework and rework_limit_reached:
        logger.warning(
            f"    ⚠️ [REWORK LIMIT REACHED] Status is DEFICIENT, but rework limit reached (Cycle {new_rework_count}/{max_rework}). "
            f"Wrapping in fallback template and continuing."
        )
        effective_needs_rework = False
        # ─── Fix A: Fallback template instead of passing raw deficient content ───
        # Per §4 llm_evaluation_and_guardrails.md: return a pre-written safe response
        # rather than letting the user receive unverified content.
        best_effort = state.get("raw_executor_output", "") or evaluation.feedback
        evaluation.feedback = _FORCED_ACCEPT_FALLBACK_TEMPLATE.format(
            best_effort_content=best_effort
        )
        # Flag for Langfuse: human review required — response was deficient but forced through
        _forced_accept = True

    logger.info(f"    Status: {'✅ MET' if evaluation.objective_met else '❌ DEFICIENT'}")
    logger.info(f"    Scores: Tools={evaluation.tool_quality_score}, Evidence={evaluation.evidence_quality_score}, "
                f"Citations={evaluation.citation_quality_score}, Freshness={evaluation.freshness_score}")
    logger.info(f"    Correction Required: {effective_needs_rework} | Rework Cycle: {new_rework_count}")
    logger.info(f"    Directive: {evaluation.actionable_advice}\n")

    return {
        "evaluator_feedback": evaluation.feedback,
        "evaluator_notes": evaluation.actionable_advice,
        "needs_rework": effective_needs_rework,
        "rework_count": new_rework_count,
        # ─── EVAL PIPELINE BRIDGE: scores forwarded to Langfuse via chat_stream_service ───
        "tool_quality_score": evaluation.tool_quality_score,
        "evidence_quality_score": evaluation.evidence_quality_score,
        "citation_quality_score": evaluation.citation_quality_score,
        "freshness_score": evaluation.freshness_score,
        "forced_accept": _forced_accept,
        **token_update
    }
