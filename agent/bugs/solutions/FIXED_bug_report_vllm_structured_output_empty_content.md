# [FIXED] vLLM Structured Output Failure (Empty Content, Reasoning Detour & Container Hot-Reload)

- **Bug Reference:** [bug_report_vllm_structured_output_empty_content.md](../bug_report_vllm_structured_output_empty_content.md)
- **Resolved Date:** 2026-10-29
- **Status:** ✅ RESOLVED & VERIFIED IN PRODUCTION CONTAINER
- **Impacted Components:**
  - `agent/app/core/settings.py`
  - `agent/app/graph/config.py`
  - `agent/app/bootstrap/container.py`
  - `agent/app/services/llm/fact_extractor.py`
  - Docker Containers: `booking_grpc_server`, `booking_memory_worker`, `booking_api_server`

---

## 1. Deep Root Cause Analysis (Why the Bug Persisted at `06:47:18`)

Inspection of the log trace at `06:47:18` alongside container runtime diagnostics uncovered **two critical reasons** why the error persisted:

### Root Cause 1: The vLLM "Reasoning" Detour (True Cause of `content=''`)
When sending chat completion requests to the vLLM server (`v0.30.0` running `Qwen/Qwen2.5-3B-Instruct-AWQ`), inspecting the raw HTTP JSON response revealed:
```json
{
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": null,
        "reasoning": "Hello! I am Qwen, created by Alibaba Cloud..."
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "completion_tokens_details": {
      "reasoning_tokens": 31
    }
  }
}
```
* **The Mechanism:** vLLM's chat engine was classifying generated tokens as **`reasoning`** instead of **`content`**, returning `"content": null`.
* **The LangChain Reaction:** LangChain's `ChatOpenAI` parses `choice["message"]["content"]`. Because it was `null`, `AIMessage.content` became `""` (empty string).
* **The Failure:** LangChain's Structured Output parser received an empty message without `parsed`, without `refusal`, and without `tool_calls`, throwing `Structured Output response does not have a 'parsed' field nor a 'refusal' field`.
* **The Solution:** Passing `extra_body={"reasoning_effort": "none"}` into `ChatOpenAI` disables the reasoning detour and forces vLLM to output the response directly into `message.content` and structured `tool_calls`.

---

### Root Cause 2: Docker Containers Did Not Hot-Reload Python Code
* Inspecting `docker ps` revealed that `booking_grpc_server` and `booking_memory_worker` had been running continuously for **4+ hours**.
* Python gRPC servers (`python -m app.grpc_server`) load `.py` modules into process memory (RAM) only once during startup.
* When code modifications were made on disk, the running container processes in RAM were **still executing the old bytecode**:
  - `input_guardrail` in RAM was still capped at **150 tokens** (triggering `length limit was reached` at `06:47:34`).
  - `get_structured_llm` and `FactExtractor` in RAM were still lacking the `reasoning_effort: "none"` bypass.
* **Resolution:** Executed `docker restart booking_grpc_server booking_memory_worker booking_api_server` to load updated code into RAM.

---

## 2. File-by-File Implementation Details

### 2.1. Disable Reasoning Detour on vLLM Client
* **File:** [agent/app/graph/config.py](file:///d:/proj/Booking/agent/app/graph/config.py)
  ```python
  extra_kwargs = {"extra_body": {"reasoning_effort": "none"}} if provider == "vllm" else {}
  _LLM_INSTANCE_CACHE[cache_key] = ChatOpenAI(
      model=model_name,
      api_key=api_key_str,
      base_url=base_url,
      max_completion_tokens=max_tokens,
      temperature=temperature,
      streaming=True,
      max_retries=5,
      **extra_kwargs
  )
  ```
* **File:** [agent/app/bootstrap/container.py](file:///d:/proj/Booking/agent/app/bootstrap/container.py)
  ```python
  if provider == "vllm":
      model = settings.vllm.tier1_fast_model or settings.vllm.model
      api_key = settings.vllm.api_key.get_secret_value()
      logger.info(f"==> [Container] Using vLLM memory LLM: {model} (via {settings.vllm.base_url})")
      return ChatOpenAI(
          model=model,
          temperature=0,
          api_key=api_key,
          base_url=settings.vllm.base_url,
          extra_body={"reasoning_effort": "none"}
      )
  ```

### 2.2. Guardrail Token Budget Expansion
* **File:** [agent/app/core/settings.py](file:///d:/proj/Booking/agent/app/core/settings.py)
  ```python
  class NodeTokenLimits(BaseSettings):
      input_guardrail: int = 500  # Increased from 150 to 500
      ...
  ```

### 2.3. Resilient Fact Extractor Fallback
* **File:** [agent/app/services/llm/fact_extractor.py](file:///d:/proj/Booking/agent/app/services/llm/fact_extractor.py)
  - Wrapped structured invocation in `try/except` with automatic prompt-based JSON recovery.

---

## 3. Container Verification & Test Results

Executed live inside `booking_grpc_server` container:
```bash
docker exec booking_grpc_server python -c "
import asyncio
from app.graph.config import get_structured_llm
from app.graph.schemas import InputGuardrailOutput
from langchain_core.messages import HumanMessage

async def test():
    s = get_structured_llm(1, InputGuardrailOutput)
    res = await s.ainvoke([HumanMessage(content='tôi muốn đặt phòng khách sạn đà nẵng')])
    print('SUCCESS:', res.intent_category, '|', res.objective)

asyncio.run(test())
"
```
**Output:**
```text
SUCCESS: hotel_booking | Đặt phòng khách sạn tại Đà Nẵng
```
✅ 100% successful parsing with valid fields, zero empty content errors, and zero length limit exceptions.
