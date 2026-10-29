# [FIXED] LangGraph Recursion Limit, Fact Checker Overflow & Model Degradation

- **Bug Reference:** [bug_report_langgraph_recursion_limit.md](../bug_report_langgraph_recursion_limit.md)
- **Resolved Date:** 2026-10-29
- **Resolution Status:** ✅ IMPLEMENTED & RESOLVED
- **Impacted Components:**
  - `agent/app/core/settings.py`
  - `agent/app/graph/nodes/evaluator.py`
  - `agent/app/graph/nodes/executor.py`
  - `agent/app/graph/nodes/extractor.py`
  - `agent/app/graph/nodes/planner.py`
  - `agent/app/graph/workflow.py`
  - `agent/app/services/streaming/chat_stream_service.py`
  - `agent/workflow.md`

---

## 1. Executive Summary of Changes

To resolve the crash caused by `GRAPH_RECURSION_LIMIT` and the model reasoning degradation issues encountered with `Qwen/Qwen2.5-3B-Instruct-AWQ`, the following targeted architectural and prompt fixes were implemented:

1. **Expanded Token Budget for Fact Checker:**
   - Increased `fact_checker` max token limit from `300` to `1000` in [agent/app/core/settings.py](../../app/core/settings.py) to prevent JSON cutoff during structured validation.
2. **Enforced Strict Language Matching Across System Prompts:**
   - Injected strict language matching constraints into [agent/workflow.md](../../workflow.md), [agent/app/graph/nodes/executor.py](../../app/graph/nodes/executor.py), [agent/app/graph/nodes/extractor.py](../../app/graph/nodes/extractor.py), and [agent/app/graph/nodes/planner.py](../../app/graph/nodes/planner.py) to prevent the model from drifting into Chinese or mixing languages.
3. **Optimized Rework Loop Mechanism for 3B LLMs (Graceful Degradation):**
   - Configured `max_rework_cycles` in settings.  
   - Updated [agent/app/graph/nodes/evaluator.py](../../app/graph/nodes/evaluator.py) and [agent/app/graph/workflow.py](../../app/graph/workflow.py): if the evaluation status remains `DEFICIENT` after reaching the rework cycle ceiling, the evaluator now explicitly accepts the current executor output (`needs_rework = False`) and proceeds directly to the next task or final synthesis instead of attempting further unproductive retries.
4. **Configured Graph Recursion Limit in Streaming:**
   - Added `"recursion_limit": 100` to `trace_config` in [agent/app/services/streaming/chat_stream_service.py](../../app/services/streaming/chat_stream_service.py) to comfortably accommodate multi-task ReAct plans with tools and reflection steps.

---

## 2. File-by-File Implementation Details

### 2.1. Fact Checker Token Headroom Expansion
* **File:** [agent/app/core/settings.py](../../app/core/settings.py)
* **Change:**
  ```python
  class NodeTokenLimits(BaseSettings):
      model_config = SettingsConfigDict(env_file=".env", env_prefix="NODE_MAX_TOKENS_", extra="ignore")
      input_guardrail: int = 150
      support_agent: int = 500
      planner_agent: int = 600
      travel_react_agent: int = 800
      finding_extractor: int = 400
      fact_checker: int = 1000  # Increased from 300 to 1000 to prevent JSON truncation
      evaluator_agent: int = 500
      final_synthesizer: int = 1000
      clarification_agent: int = 200
  ```
* **Rationale:** The `FactCheckResult` structured output includes lists of ungrounded claims, contradiction descriptions, and consistency scores. 300 tokens was insufficient for long itineraries, causing premature generation cutoffs. 1000 tokens provides reliable headroom.

---

### 2.2. Strict Anti-Drift Language Constraints
* **Files:**
  - [agent/workflow.md](../../workflow.md): Added strict anti-drift directives to the master manifest:
    ```markdown
    * **Dynamic Response Language & Strict Language Matching:** Adapt the response language dynamically based on the user's input. If the user initiates the conversation or queries in English, respond strictly in English. If the user queries in Vietnamese, respond strictly in Vietnamese.
    * **Strict Anti-Drift Rule:** Under NO circumstances should any agent, executor, or extractor switch or drift to Chinese, or mix Chinese characters into a Vietnamese or English query response. All generated thoughts, answers, and findings must strictly match the user's input language.
    ```
  - [agent/app/graph/nodes/executor.py](../../app/graph/nodes/executor.py): Added dynamic prompt injection for `travel_react_agent`:
    ```python
    f"CRITICAL LANGUAGE RULE: The user is communicating in '{detected_language}'. You MUST think, act, and formulate your FINAL ANSWER strictly in '{detected_language}'. Under NO circumstance should you switch, drift, or mix into Chinese or any other language.\n\n"
    ```
    Updated `COMPACT_AGENT_REMINDER` to enforce user language output.
  - [agent/app/graph/nodes/extractor.py](../../app/graph/nodes/extractor.py): Added instruction ensuring extracted statements and summary retain the user's detected language without translation to Chinese.
  - [agent/app/graph/nodes/planner.py](../../app/graph/nodes/planner.py): Added instruction ensuring planned subtask descriptions match the user's detected language.

---

### 2.3. Rework Loop Optimization for 3B Model
* **Files:** 
  - [agent/app/core/settings.py](../../app/core/settings.py)
  - [agent/app/graph/nodes/evaluator.py](../../app/graph/nodes/evaluator.py)
  - [agent/app/graph/workflow.py](../../app/graph/workflow.py)
* **Logic:**
  When `evaluator_agent` runs:
  ```python
  new_rework_count = current_rework_count + 1 if evaluation.needs_rework else current_rework_count
  max_rework = getattr(settings, "max_rework_cycles", 2)
  rework_limit_reached = new_rework_count >= max_rework

  effective_needs_rework = evaluation.needs_rework
  if effective_needs_rework and rework_limit_reached:
      logger.warning(
          f"    ⚠️ [REWORK LIMIT REACHED] Status is DEFICIENT, but rework limit reached (Cycle {new_rework_count}/{max_rework}). "
          f"Accepting current response to continue processing."
      )
      effective_needs_rework = False
      evaluation.feedback = f"{evaluation.feedback} [Accepted: max rework cycles reached]"
  ```
  And in `workflow.py` (`route_from_evaluator`):
  ```python
  def route_from_evaluator(state: AgentState) -> str:
      if state.get("needs_rework"):
          if state.get("rework_count", 0) >= MAX_REWORK_CYCLES:
              FORCED_TERMINATION_TOTAL.labels(domain="travel_react_agent", reason="max_rework_cycles").inc()
              logger.warning(f"==> [Evaluator Route] Status DEFICIENT but reached max rework cycles ({MAX_REWORK_CYCLES}). Accepting current response and routing to task_manager.")
              return "task_manager"
          return "travel_react_agent"
      return "task_manager"
  ```
* **Result:** If the 3B model fails to meet the strict critique criteria after its allowed retry, the pipeline avoids stalling or burning steps in a regression loop. It saves the latest executor output into task memory and advances to the next task or final synthesis.

---

### 2.4. Streaming Recursion Limit Safeguard
* **File:** [agent/app/services/streaming/chat_stream_service.py](../../app/services/streaming/chat_stream_service.py)
* **Change:**
  ```python
  trace_config = {
      "recursion_limit": 100,  # Prevent GRAPH_RECURSION_LIMIT on multi-task ReAct plans
      "metadata": {
          "session_id": session_id, 
          "user_id": user_id,
          "source": source
      },
      "configurable": {
          "thread_id": f"{user_id}_{session_id}"
      }
  }
  ```
* **Rationale:** LangGraph's default limit of 25 steps is exceeded when handling 4 subtasks with multiple tool calls and evaluator nodes. Setting `recursion_limit: 100` gives ample execution headroom.

---

## 3. Verification & Expected Behavioral Impact

1. **No More Premature gRPC Crashes:**
   - Multi-step requests will no longer crash at step 25 with `GRAPH_RECURSION_LIMIT`.
2. **Fact Checking Consistency:**
   - `fact_checker` outputs complete validation JSON without `Could not parse response content as the length limit was reached`.
3. **Language Consistency:**
   - Vietnamese queries will consistently receive Vietnamese responses across all ReAct iterations, findings, and final synthesis.
4. **Predictable Rework Costs:**
   - A task will never rework more than the configured threshold. Even with low reflection scores, the system gracefully proceeds with best-effort results to complete user requests.
