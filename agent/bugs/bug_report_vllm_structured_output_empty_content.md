# [BUG REPORT] vLLM Structured Output Failure (Empty Content & Guardrail Token Truncation)

- **Date:** 2026-10-29
- **Environment:** Multi-Agent Platform (vLLM v0.30.0, LangGraph, gRPC Core Engine)
- **Log Source:** `agent/logs/agent_platform.html` (Lines 190–233)
- **Status:** **PENDING FIX**
- **Solution File:** [solutions/FIXED_bug_report_vllm_structured_output_empty_content.md](file:///d:/proj/Booking/agent/bugs/solutions/FIXED_bug_report_vllm_structured_output_empty_content.md)
- **Request Details:**
  - **User ID:** `f7309c20-ab63-4438-ac47-4c1e338ec34b`
  - **Session ID:** `uBB33aocu3DXgsogNJMesQ`
  - **Correlation ID:** `fbf2af70-3050-480c-ae30-ea5b30b3f46d`
- **Models Used:**
  - **Main / Memory LLM:** `Qwen/Qwen2.5-3B-Instruct-AWQ` (vLLM @ port 17680)

---

## 1. Executive Summary

During request execution `fbf2af70-3050-480c-ae30-ea5b30b3f46d`, multiple cognitive nodes (`input_guardrail`, `finding_extractor`, `evaluator_agent`, and the background `AsyncMemoryWorker`) encountered critical runtime parsing failures:

1. **Guardrail Failure (`05:58:09`):** `input_guardrail` failed with:
   `Could not parse response content as the length limit was reached`
   This forced the pipeline to bypass the Planner and fallback to a single unstructured task.
2. **Cascading Structured Output Crashes (`05:58:11` - `05:58:17`):**
   `finding_extractor`, `evaluator_agent`, and `AsyncMemoryWorker` failed identically with:
   ```text
   Structured Output response does not have a 'parsed' field nor a 'refusal' field.
   Received message: content='' additional_kwargs={'parsed': None, 'refusal': None} ... tool_calls=[]
   ```
   In the background memory worker, the pipeline was completely aborted (`[CRITICAL WORKER FAILURE] Data synthesis sequence aborted`).

---

## 2. Detailed Bug Analysis & Trace

### Bug A: `input_guardrail` Token Starvation (Truncation)
* **Log Entry:**
  ```text
  [2026-10-29 05:58:09] [ERROR] [CognitiveNodes] ❌ [GUARDRAIL FAILURE] Defaulting to travel framework -> Trace: Could not parse response content as the length limit was reached
  ```
* **Root Cause:**
  - In [agent/app/core/settings.py](file:///d:/proj/Booking/agent/app/core/settings.py#L147), `NodeTokenLimits.input_guardrail` is configured to `150`.
  - When `InputGuardrailOutput` generates its JSON payload (`in_domain`, `intent_category`, `complexity`, `detected_language`, `intent_confidence`, `overarching_objective`), the output tokens hit the 150-token ceiling mid-stream (`finish_reason='length'`).
  - The unclosed JSON string causes Pydantic parsing to throw a decode error, triggering the guardrail fallback.

---

### Bug B: Empty Content from vLLM on Structured Output
* **Log Entries:**
  - **Finding Extractor (`05:58:11`):**
    ```text
    [ERROR] [CognitiveNodes] ❌ [EXTRACTOR FAILURE] Falling back to raw executor text. Trace: Structured Output response does not have a 'parsed' field nor a 'refusal' field. Received message:
    content='' additional_kwargs={'parsed': None, 'refusal': None} response_metadata={'finish_reason': 'stop', 'token_usage': None, 'model_provider': 'openai', 'model_name': 'Qwen/Qwen2.5-3B-Instruct-AWQ', 'system_fingerprint': 'vllm-0.30.0-bc08da29', 'id': 'chatcmpl-af6e1d4c8ac89158'} id='lc_run--01a1863c-c03b-7eb2-b44d-dbb0d4368b56' tool_calls=[] invalid_tool_calls=[]
    ```
  - **Evaluator Agent (`05:58:13`):**
    ```text
    [ERROR] [CognitiveNodes] ❌ [EVALUATOR FAILURE] Parse error: Structured Output response does not have a 'parsed' field nor a 'refusal' field. Received message:
    content='' additional_kwargs={'parsed': None, 'refusal': None} response_metadata={'finish_reason': 'stop', ...} id='lc_run--01a1863c-c3c5-7db2-ae54-d48dfe4968f0' tool_calls=[] invalid_tool_calls=[]
    ```
  - **AsyncMemoryWorker (`05:58:17`):**
    ```text
    [ERROR] [AsyncMemoryWorker] ❌ [CRITICAL WORKER FAILURE] Data synthesis sequence aborted for User: f7309c20-ab63-4438-ac47-4c1e338ec34b | Trace: Structured Output response does not have a 'parsed' field nor a 'refusal' field. Received message:
    content='' additional_kwargs={'parsed': None, 'refusal': None} response_metadata={'token_usage': {'completion_tokens': 79, 'prompt_tokens': 74, 'total_tokens': 153, 'completion_tokens_details': {'reasoning_tokens': 78}}, 'model_name': 'Qwen/Qwen2.5-3B-Instruct-AWQ', 'finish_reason': 'stop'}
    ```
* **Root Cause:**
  1. **Function Calling Mismatch on Small Model:** LangChain's `with_structured_output(schema)` defaults to `method="function_calling"`. It sends `tools=[schema]` to the vLLM OpenAI-compatible endpoint.
  2. **Reasoning Token Consumption:** As revealed in the memory worker log (`completion_tokens: 79`, `reasoning_tokens: 78`), the 3B model spent 78 tokens generating reasoning/thought tokens instead of emitting formatted tool call tokens.
  3. **Empty Message Payload:** vLLM concluded generation (`finish_reason='stop'`), emitting `content=''` and `tool_calls=[]`.
  4. **Parser Explosion:** LangChain received neither a tool call nor text in `content`. It could not populate `parsed` or `refusal`, raising `OutputParserException`.
  5. **Unhandled Exception in Worker:** While graph nodes had try/except blocks to fallback, `FactExtractor.extract()` in `AsyncMemoryWorker` did not catch structured output exceptions, causing complete task abort.

---

## 3. Scope of Impact

* **Pipeline Quality Degradation:** Guardrail fallback meant requests bypassed structured planning and intent classification.
* **Loss of Reflection & Quality Metrics:** Evaluator and Extractor nodes were bypassed, rendering reflection scores moot.
* **Memory Subsystem Failure:** Long-term factual insights from the conversation were permanently lost due to worker abortion.
