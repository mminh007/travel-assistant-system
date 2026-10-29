# [BUG REPORT & RESOLUTION] vLLM "auto" Tool Choice Error (Missing Parser & Tool Flags)

- **Date:** 2026-10-29
- **Environment:** Multi-Agent Platform (vLLM on Vast.ai, LangGraph, gRPC Core Engine, ASP.NET Core SignalR)
- **Log Source:** .NET Client Trace (`Grpc.Net.Client.Internal.GrpcCall`) & Python Server Logs (`agent_grpc`)
- **Status:** **RESOLVED**
- **Impact Severity:** **HIGH** (Completely blocks any Agent workflows requiring Tool Calling / Function Calling)
- **Models Affected:**
  - `Qwen/Qwen2.5-3B-Instruct-AWQ` (vLLM serving instance @ port 18000 / proxy port 27613)

---

## 1. Executive Summary

When a user in the Booking Website submitted an actionable travel query (e.g., *"Tìm khách sạn tại Đà Nẵng"*), the request was routed through SignalR (`ChatHub.cs`) to the backend Python Agent via gRPC (`StreamChat`). The Agent's cognitive architecture correctly classified the intent and transitioned to the ReAct Executor (`node_travel_react_agent`) to invoke external booking tools.

However, the execution abruptly terminated with a gRPC `StatusCode.INTERNAL` error:

```text
info: Grpc.Net.Client.Internal.GrpcCall[3]
      Call failed with gRPC error status. Status code: 'Internal', Message: 'Error code: 400 - {'error': {'message': '"auto" tool choice requires --enable-auto-tool-choice and --tool-call-parser to be set', 'type': 'BadRequestError', 'param': None, 'code': 400}}'
```

The root cause was traced to the **vLLM server instance hosted on Vast.ai**. Although the model was running and responding to plain-text completions, the vLLM serving process was launched without tool-calling capabilities (`--enable-auto-tool-choice` and `--tool-call-parser`). When LangChain attempted to bind tools and issued an OpenAI-compatible payload with `tool_choice="auto"`, vLLM rejected the HTTP request with status `400 Bad Request`.

---

## 2. Error Reproduction & Raw Log Analysis

### 2.1. Client-Side Error (.NET SignalR Hub)
```text
info: Grpc.Net.Client.Internal.GrpcCall[3]
      Call failed with gRPC error status. Status code: 'Internal', 
      Message: 'Error code: 400 - {'error': {'message': '"auto" tool choice requires --enable-auto-tool-choice and --tool-call-parser to be set', 'type': 'BadRequestError', 'param': None, 'code': 400}}'
```

### 2.2. Direct Endpoint Reproduction (vLLM HTTP API)
Issuing a direct POST request to `http://<VAST_IP>:<PORT>/v1/chat/completions` containing tool schemas reproduces the exact failure:

```python
import httpx

payload = {
    "model": "Qwen/Qwen2.5-3B-Instruct-AWQ",
    "messages": [{"role": "user", "content": "Tìm phòng khách sạn Đà Nẵng"}],
    "tools": [{
        "type": "function",
        "function": {
            "name": "search_hotels",
            "description": "Search available hotels by location",
            "parameters": {
                "type": "object", 
                "properties": {"location": {"type": "string"}},
                "required": ["location"]
            }
        }
    }],
    "tool_choice": "auto"
}

# Response:
# HTTP/1.1 400 Bad Request
# {"error":{"message":"\"auto\" tool choice requires --enable-auto-tool-choice and --tool-call-parser to be set","type":"BadRequestError","param":null,"code":400}}
```

---

## 3. Root Cause Analysis

### 3.1. How LangChain Triggers Tool Calls
In `agent/app/graph/nodes/react_executor.py` and `planner.py`, the LLM is initialized and attached to MCP tools:
```python
llm_with_tools = llm.bind_tools(tools)
```
Under the hood, LangChain's `ChatOpenAI` implementation converts Python tool definitions into OpenAI-compatible JSON schemas (`type: "function"`). Under the OpenAI API specification:
- Whenever `tools` are passed in the request body, `tool_choice` automatically defaults to `"auto"`.
- This informs the server that the model may either reply with a natural language message or emit structured tool call arguments.

### 3.2. Why vLLM Rejects the Request
1. **Default vLLM Behavior:** By default, vLLM runs in pure text completion mode. It does not load token parsers or register tool templates unless explicitly commanded to do so via CLI flags.
2. **Missing CLI Arguments:** In `agent/serving/vllm/configs/start_awq_kv_fp8.sh`, the serving command was configured with quantization, chunked prefill, and prefix caching, but omitted the necessary tool flags:
   ```bash
   # Incomplete command in original script:
   vllm serve "$MODEL" \
     --host 0.0.0.0 \
     --port "$PORT" \
     --dtype float16 \
     --quantization awq_marlin \
     --max-model-len 4096 \
     --gpu-memory-utilization "$GPU_UTIL" \
     --enable-chunked-prefill \
     --enable-prefix-caching
     # Missing: --enable-auto-tool-choice
     # Missing: --tool-call-parser
   ```
3. When vLLM's HTTP request validator inspected the incoming request and encountered `tool_choice="auto"`, it verified whether `auto_tool_choice` was enabled and whether a parser was registered. Finding neither, it immediately aborted with HTTP 400.

---

## 4. In-Depth Explanation of Required vLLM Flags

### 4.1. `--enable-auto-tool-choice`

#### What It Does:
This flag enables vLLM's server engine to support dynamic tool routing. It permits incoming API requests to specify `tool_choice="auto"` (or `tool_choice="required"`).

#### Why It Is Necessary:
Without this flag, vLLM treats tool-enabled requests as invalid configurations to prevent unexpected model behavior. When `--enable-auto-tool-choice` is activated:
- The API server accepts the `tools` list in `/v1/chat/completions`.
- It prompts the model using an integrated chat template that defines available tools.
- It permits the model to freely decide whether to invoke zero, one, or multiple tools, or simply respond with text.

---

### 4.2. `--tool-call-parser`

#### What It Does:
The `--tool-call-parser` flag designates the specific regex/grammar parser that interprets the model's raw token generation stream and extracts function calls into OpenAI-compatible JSON responses.

#### Why a Parser Is Needed:
OpenAI models output structured tool calls natively via proprietary API layers. Open-weight models (like Qwen, Llama, Mistral), however, output tool calls as **regular text tokens** wrapped inside special delimiters defined by their respective prompt templates.

For example, when `Qwen2.5` decides to call a function, it generates text like:
```text
<tool_call>
{"name": "search_hotels", "arguments": {"location": "Da Nang"}}
</tool_call>
```
Without a tool call parser:
- The client receives raw XML/markdown tags as plain text.
- LangChain / LangGraph cannot identify that a tool needs execution, breaking the ReAct loop.

With `--tool-call-parser` enabled:
- vLLM intercepts the `<tool_call>` output tokens during generation.
- It parses and deserializes the JSON string into standard OpenAI response format:
  ```json
  "tool_calls": [
    {
      "id": "call_abc123",
      "type": "function",
      "function": {
        "name": "search_hotels",
        "arguments": "{\"location\": \"Da Nang\"}"
      }
    }
  ]
  ```

#### Supported Parsers & Model Compatibility Matrix:

| Parser Value | Intended Model Families | Tool Delimiter / Syntax Style | Reference |
| :--- | :--- | :--- | :--- |
| **`hermes`** *(Official for Qwen2.5)* | **`Qwen/Qwen2.5-*`**, `Qwen/QwQ-32B`, `NousResearch/Hermes` | `<tool_call>\n{"name": ..., "arguments": ...}\n</tool_call>` | [vLLM Tool Calling Docs](https://docs.vllm.ai/en/latest/features/tool_calling/#qwen-models) |
| `mistral` | `Mistral-7B-Instruct-v0.3`, `Mixtral` | `[TOOL_CALLS] [{"name": ..., "arguments": ...}]` | Official Mistral formats |
| `llama3_json` | `Meta-Llama-3.1`, `Meta-Llama-3.2` | `<|python_tag|>` or JSON schema blocks | Llama 3.x Tool format |
| `pythonic` | Llama Pythonic tool calling | Function calls formatted as raw Python syntax | |
| `qwen3_coder` | Experimental Qwen3 Coder / XML models | Specific XML tags tailored for code agents | |

> [!IMPORTANT]
> **Official Rule for Qwen2.5:**
> According to the official [vLLM Documentation](https://docs.vllm.ai/en/latest/features/tool_calling/#qwen-models) and [Qwen Official Documentation](https://qwen.readthedocs.io/en/latest/framework/function_call.html#vllm):
> *"For Qwen2.5, the chat template in `tokenizer_config.json` has already included support for the Hermes-style tool use. Therefore, you can use the `hermes` parser to enable tool calls for Qwen models (`Qwen/Qwen2.5-*`, `Qwen/QwQ-32B`). Flags: `--enable-auto-tool-choice --tool-call-parser hermes`"*

## 5. Resolution & Implementation Steps

### 5.1. Restarting vLLM on Vast.ai (Server-Side Fix)

Connect to the Vast.ai instance via SSH and restart the vLLM serving process with both required flags:

```bash
# 1. Terminate the existing vLLM process occupying port 18000
fuser -k 18000/tcp || pkill -f "vllm serve"

# 2. Launch vLLM with auto tool choice and hermes parser enabled
nohup vllm serve Qwen/Qwen2.5-3B-Instruct-AWQ \
  --host 127.0.0.1 \
  --port 18000 \
  --dtype float16 \
  --quantization awq_marlin \
  --max-model-len 4096 \
  --gpu-memory-utilization 0.50 \
  --enable-chunked-prefill \
  --max-num-batched-tokens 512 \
  --enable-prefix-caching \
  --max-num-seqs 64 \
  --enable-auto-tool-choice \
  --tool-call-parser hermes \
  --served-model-name "Qwen/Qwen2.5-3B-Instruct-AWQ" "Qwen2.5-3B-Instruct-AWQ" > llm.log 2>&1 &

# 3. Monitor startup logs
tail -f llm.log
```

Wait until the log confirms:
```text
INFO: Application startup complete.
```

---

### 5.2. Updating Local Repository Scripts

All startup scripts inside `agent/serving/vllm/configs/` have been updated to ensure future deployments automatically include these flags:

1. [`agent/serving/vllm/configs/start_awq_kv_fp8.sh`](file:///d:/proj/Booking/agent/serving/vllm/configs/start_awq_kv_fp8.sh):
   ```bash
     --enable-prefix-caching \
     --max-num-seqs 64 \
     --enable-auto-tool-choice \
     --tool-call-parser hermes \
     --served-model-name "$MODEL" "$(basename "$MODEL")"
   ```
2. [`agent/serving/vllm/configs/start_awq.sh`](file:///d:/proj/Booking/agent/serving/vllm/configs/start_awq.sh)
3. [`agent/serving/vllm/configs/start_awq_chunked.sh`](file:///d:/proj/Booking/agent/serving/vllm/configs/start_awq_chunked.sh)
4. [`agent/serving/vllm/configs/start_awq_prefix.sh`](file:///d:/proj/Booking/agent/serving/vllm/configs/start_awq_prefix.sh)
5. [`agent/serving/vllm/configs/start_baseline.sh`](file:///d:/proj/Booking/agent/serving/vllm/configs/start_baseline.sh)

---

## 6. Verification & End-to-End Validation

### 6.1. Unit Verification (Python HTTP Test)
A validation script was executed against the running vLLM server with tools attached:

```python
import httpx

token = "b989845eb84acde8c2841e2b61d7b87b06214d1317ee460b798c155782d2b760"
headers = {"Authorization": f"Bearer {token}"}
payload = {
    "model": "Qwen/Qwen2.5-3B-Instruct-AWQ",
    "messages": [{"role": "user", "content": "Tìm khách sạn tại Đà Nẵng"}],
    "tools": [{
        "type": "function",
        "function": {
            "name": "search_hotels",
            "description": "Search available hotels in a city",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"]
            }
        }
    }],
    "tool_choice": "auto"
}

r = httpx.post("http://151.237.25.16:27613/v1/chat/completions", headers=headers, json=payload, timeout=30.0)
assert r.status_code == 200
data = r.json()
assert "tool_calls" in data["choices"][0]["message"]
```

**Result:** `HTTP 200 OK` — `tool_calls` generated and parsed properly by vLLM.

---

### 6.2. End-to-End Workflow Verification
1. User asks: *"Tìm khách sạn tại Đà Nẵng"* on Website.
2. SignalR transmits to `booking_grpc_server`.
3. LangGraph invokes `node_travel_react_agent` with bound MCP tools.
4. vLLM successfully streams tool call arguments without error.
5. Tool execution retrieves real hotel data, synthesizes the final message, and streams back to the browser UI.

---

## 7. Key Takeaways & Recommendations

1. **Always Match Model Architecture with Parser:** When deploying any model on vLLM that participates in LangGraph / Agentic workflows, verify the model's chat template format and supply the matching `--tool-call-parser`.
2. **Flag Dependency:** `--enable-auto-tool-choice` cannot function alone; it strictly requires `--tool-call-parser` to be set.
3. **Keep Deployment Scripts Synchronized:** Never manually execute CLI commands on remote GPU instances without recording the exact flags into version-controlled repository configuration files.



---

## 8. Deep-Dive Re-Analysis: Dissecting the "Empty Content & Reasoning" Phenomenon

**Date of Re-Analysis:** 2026-10-29  
**Verdict: `--tool-call-parser hermes` is 100% correct for Qwen2.5. The subsequent `content=''` failure is caused by Small Model Limitations during `with_structured_output()` Function Calling, NOT a vLLM/Qwen version conflict or parser mismatch.**

### 8.1. Confirmation of Official Standard
Official documentation from both **vLLM** and the **Alibaba Qwen team** confirms:
- Qwen2.5 Instruct models natively embed the Hermes tool calling template in their `tokenizer_config.json`.
- The only official and supported parser for Qwen2.5 tool calling in vLLM is `--tool-call-parser hermes`.
- There is no such parser as `qwen2vl` for general text tool calling (Qwen2-VL also utilizes Hermes format). Any suggestion to replace `hermes` with a different parser on vLLM would result in invalid parser arguments on startup.

### 8.2. Why Did `content=''` and `reasoning_tokens: 78` Occur?
When evaluating why subsequent runs threw `Structured Output response does not have a 'parsed' field nor a 'refusal' field` with `content=''`, the logs reveal:

1. **Function Calling vs. Small Model Capacity (3B):**
   - LangChain's `model.with_structured_output(Schema)` defaults to `method="function_calling"`.
   - It binds the Pydantic schema as a synthetic function definition and sets `tool_choice="auto"`.
   - `Qwen2.5-3B-Instruct` is a lightweight 3-billion-parameter model. When presented with complex structured output schemas (e.g., `FindingExtractorOutput` or `LongTermFactSchema`), the 3B model often fails to format the exact `<tool_call>` XML tag wrapper required by the Hermes parser.

2. **Reasoning Channel Segregation in vLLM:**
   - Instead of emitting `<tool_call>...<\/tool_call>`, the 3B model began generating intermediate reasoning / thought tokens (accounting for `reasoning_tokens: 78` out of 79 total tokens).
   - vLLM's `Hermes2ProToolParser` intercepts scratchpad / reasoning tokens into the `reasoning` channel and looks for `<tool_call>` tags for `tool_calls`.
   - Because no `<tool_call>` tag was found, `tool_calls` was returned as empty (`[]`), and because output was segregated into reasoning, `content` was returned as empty (`''`).

3. **Downstream LangChain Crash:**
   - LangChain's output parser checked `content` (empty) and `tool_calls` (empty).
   - It found neither a valid message nor a tool call payload, throwing `OutputParserException`.

### 8.3. Correct Resolution Strategy

| Component | Responsibility | Action / Fix |
| :--- | :--- | :--- |
| **vLLM Server Flags** | Tool Calling Serving | **KEEP `--tool-call-parser hermes` and `--enable-auto-tool-choice`**. This is mandatory for real tool calling (e.g., ReAct Travel Agent searching hotels). |
| **Structured Output Nodes** | Schema Extraction on Small Models | For models $\le$ 7B, do NOT use `method="function_calling"`. Use **`method="json_mode"`** or explicit prompt-based JSON schemas. |
| **Reasoning Parameter** | Suppress unwanted reasoning routing | Pass `extra_body={"reasoning_effort": "none"}` in `ChatOpenAI` so vLLM does not segregate tokens into the reasoning channel for extraction tasks. |
| **Worker Error Handling** | Fault-Tolerance | Implement fallback try/except in `FactExtractor.extract()` to gracefully recover even if structured parsing encounters an anomaly. |
