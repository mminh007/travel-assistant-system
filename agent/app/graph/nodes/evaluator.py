# app/graph/nodes/evaluator.py
import json
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
        result, usage = await invoke_llm_with_limit(1, structured_checker, [HumanMessage(content=check_prompt)], config, max_tokens_override=settings.node_limits.fact_checker, node_name="fact_checker")

        if not result.is_consistent:
            logger.warning(f"⚠️ [FACT CHECK] Contradictions detected: {result.contradictions}")

        token_update = update_token_usage(state, usage, node_name="fact_checker")

        feedback = f"[Fact Check] Consistency: {result.consistency_score:.2f}. {'; '.join(result.contradictions)}" if result.contradictions else ""

        return {
            "fact_check_result": result.model_dump(),
            "evaluator_feedback": feedback,
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
