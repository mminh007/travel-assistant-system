# app/graph/nodes/extractor.py
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

from app.graph.state import AgentState
from app.graph.config import get_structured_llm, invoke_llm_with_limit
from app.graph.schemas import ExecutorOutput
from app.graph.utils import update_token_usage
from app.core.settings import settings
from app.core.logger import setup_app_logger

logger = setup_app_logger("CognitiveNodes")


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
        ], config, max_tokens_override=settings.node_limits.finding_extractor, node_name="finding_extractor")
        raw_summary = extraction.result_summary
        findings = [f.model_dump() for f in extraction.findings]
        logger.info(f"    Extracted {len(findings)} finding(s). Summary: '{raw_summary[:80]}...'")
        token_update = update_token_usage(state, usage, node_name="finding_extractor")
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
