import os
import functools
import tiktoken
from app.graph.state import AgentState
from app.core.logger import setup_app_logger
from app.core.metrics import NODE_INPUT_TOKENS, NODE_OUTPUT_TOKENS

logger = setup_app_logger("CognitiveUtils")

def update_token_usage(state: AgentState, usage, node_name: str = "unknown") -> dict:
    """
    Updates token usage in state AND emits Prometheus metrics.
    node_name: Node name for per-node analysis in Grafana.
    
    LIMITATION: Cost figures are GPT-4o-based approximations and may be 
    highly inaccurate for other models (e.g. Claude).
    """
    cost_in = usage.input_tokens * (0.15 if usage.tier == 1 else 5.0) / 1000000
    cost_out = usage.output_tokens * (0.60 if usage.tier == 1 else 15.0) / 1000000
    cost = cost_in + cost_out

    tier_str = str(usage.tier)

    # ─── PROMETHEUS METRICS ───
    NODE_INPUT_TOKENS.labels(node_name=node_name, tier=tier_str).observe(usage.input_tokens)
    NODE_OUTPUT_TOKENS.labels(node_name=node_name, tier=tier_str).observe(usage.output_tokens)

    # ─── STRUCTURED LOG (TOKEN_AUDIT) ───
    # Fixed format so the analyzer script can parse it
    logger.info(
        f"[TOKEN_AUDIT] "
        f"node={node_name} | "
        f"tier={usage.tier} | "
        f"in={usage.input_tokens} | "
        f"out={usage.output_tokens} | "
        f"cost_usd={cost:.6f}"
    )

    tier_prefix = f"tier{usage.tier}"
    in_key = f"{tier_prefix}_input_tokens"
    out_key = f"{tier_prefix}_output_tokens"
    return {
        in_key: (state.get(in_key) or 0) + usage.input_tokens,
        out_key: (state.get(out_key) or 0) + usage.output_tokens,
        "estimated_cost_usd": (state.get("estimated_cost_usd") or 0.0) + cost
    }

def prune_messages_by_token_limit(messages: list, max_tokens: int, model_name: str) -> list:
    """Ensures message history strictly respects context window boundaries."""
    try:
        encoding = tiktoken.encoding_for_model(model_name)
    except KeyError:
        encoding = tiktoken.get_encoding("o200k_base")

    total_tokens = 0
    keep_messages = []
    for msg in reversed(messages):
        content = msg.content if isinstance(msg.content, str) else ""
        msg_tokens = len(encoding.encode(content))
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
