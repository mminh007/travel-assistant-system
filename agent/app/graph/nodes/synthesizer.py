# app/graph/nodes/synthesizer.py
from langchain_core.messages import HumanMessage, RemoveMessage
from langchain_core.runnables import RunnableConfig

from app.graph.state import AgentState
from app.graph.config import get_llm_instance, invoke_llm_with_limit
from app.graph.utils import update_token_usage
from app.core.metrics import (
    GRAPH_ITERATIONS,
    ITERATIONS_BY_COMPLEXITY,
    TOOL_CALLS_BY_COMPLEXITY,
    REWORK_CYCLES_BY_COMPLEXITY,
)
from app.core.settings import settings
from app.core.logger import setup_app_logger

logger = setup_app_logger("CognitiveNodes")

FINDING_CONFIDENCE_THRESHOLD = 0.5


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

    final_response, usage = await invoke_llm_with_limit(2, get_llm_instance(2, config), [HumanMessage(content=synthesis_prompt)], config, max_tokens_override=settings.node_limits.final_synthesizer, node_name="final_synthesizer")

    # Clean any leading/trailing markdown code fences as a failsafe
    if final_response and hasattr(final_response, "content") and isinstance(final_response.content, str):
        content = final_response.content.strip()
        if content.startswith("```markdown") and content.endswith("```"):
            content = content[11:-3].strip()
        elif content.startswith("```") and content.endswith("```"):
            content = content[3:-3].strip()
        final_response.content = content

    total_iterations = state.get("iteration_count", 0)
    complexity = state.get("complexity") or "medium"
    GRAPH_ITERATIONS.labels(domain=state.get("current_domain", "general_memory")).observe(total_iterations)
    ITERATIONS_BY_COMPLEXITY.labels(complexity=complexity).observe(total_iterations)
    TOOL_CALLS_BY_COMPLEXITY.labels(complexity=complexity).observe(state.get("tool_call_count", 0))
    REWORK_CYCLES_BY_COMPLEXITY.labels(complexity=complexity).observe(state.get("rework_count", 0))

    logger.info("    Process Complete. Handshake ready.\n\n")

    return {
        "messages": [final_response],
        **update_token_usage(state, usage, node_name="final_synthesizer")
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
    from langchain_core.messages import HumanMessage as _HM  # local import to avoid circular
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
            if getattr(state["messages"][i], "type", "") == "human" or isinstance(state["messages"][i], _HM):
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
