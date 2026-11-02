# 📊 Prometheus & Grafana Metrics Tracking Reference
## Travel Assistant System — Multi-Agent & Hybrid RAG Stack

The observability system of the Travel Assistant Agent is designed according to **Prometheus Metrics** standards, continuously tracking 8 mission-critical operational groups:

1. **Traffic & End-to-End Latency (HTTP SSE & gRPC Streaming)**
2. **LangGraph Node Execution & LLM Inference**
3. **Programmatic Safeguards & ReAct Loops**
4. **Semantic Caching, Embeddings & Hybrid RAG**
5. **Token Governance & Cost Attribution**
6. **Dynamic Complexity Routing**
7. **vLLM Serving Engine Performance (GPU, KV Cache, Latency)**
8. **k6 Distributed Load Testing Metrics**

---

## 1. Traffic & End-to-End Latency

Declared in [`app/core/metrics.py`](../app/core/metrics.py).

| Metric Name | Type | Labels / Dimensions | Description & Significance |
| :--- | :---: | :--- | :--- |
| `sse_active_streams` | Gauge | *None* | **Current active HTTP SSE connection count.** Monitors real-time web users connected via SSE streaming. |
| `sse_disconnect_total` | Counter | `reason` (`completed`, `abrupt_client_disconnect`, `cache_hit`, `error`) | **Total closed SSE sessions**, classified by termination reason. Helps detect client drop-off rates during streaming. |
| `grpc_active_streams` | Gauge | *None* | **Current active gRPC bi-directional / server streams.** Monitors inter-service and high-performance client load. |
| `grpc_errors_total` | Counter | *None* | **Total runtime exceptions encountered in gRPC pipeline.** Measures gRPC channel stability. |
| `agent_requests_total` | Counter | `source` (`http`, `grpc`), `status` (`completed`, `cache_hit`, `error`, `cancelled`) | **Total requests sent to the Agent.** Computes Request Rate (req/s), Throughput, and Success/Error rates across protocols. |
| `agent_request_duration_seconds` | Histogram | `source`, `status`<br>Buckets: `0.05s` → `60.0s` | **End-to-End Request Latency.** Measured from incoming request receipt to the final chunk streamed. Used for SLA p50, p95, and p99 tracking. |
| `agent_time_to_first_token_seconds` | Histogram | `source`, `cache_status` (`hit`, `miss`)<br>Buckets: `0.02s` → `20.0s` | **Time to First Token (TTFT).** Duration from question submission to the very first token appearing on user screen. Reflects interactive responsiveness (cache hits reduce TTFT from ~2s to <50ms). |

---

## 2. LangGraph Node Execution & LLM Inference

Declared in [`app/core/metrics.py`](../app/core/metrics.py).

| Metric Name | Type | Labels / Dimensions | Description & Significance |
| :--- | :---: | :--- | :--- |
| `agent_node_duration_seconds` | Histogram | `node_name`<br>Buckets: `0.05s` → `20.0s` | **Execution duration per LangGraph Node** (`guardrail`, `planner`, `travel_react_agent`, `finding_extractor`, `fact_checker`, `evaluator_agent`, `task_manager`, `final_synthesizer`). Identifies workflow bottlenecks. |
| `agent_llm_call_duration_seconds` | Histogram | `node_name`, `tier` (`tier1`, `tier2`, `tier3`), `status` (`ok`, `truncated`, `error`)<br>Buckets: `0.05s` → `30.0s` | **Raw LLM inference latency**, inclusive of concurrency semaphore wait time. Measures model responsiveness per node and per tier. |
| `agent_llm_call_errors_total` | Counter | `node_name`, `tier`, `error_type` | **Total failed LLM calls**, partitioned by node, model tier, and error class (e.g., timeout, rate_limit, invalid_json, vLLM_error). |
| `agent_tool_call_duration_seconds` | Histogram | `tool_name`, `status`<br>Buckets: `0.01s` → `10.0s` | **Tool execution latency.** Tracks performance of local SQLite lookups, Qdrant queries, MCP tools, Tavily web search, and Amadeus API calls. |

---

## 3. Programmatic Safeguards & ReAct Loops

Declared in [`app/core/metrics.py`](../app/core/metrics.py).

| Metric Name | Type | Labels / Dimensions | Description & Significance |
| :--- | :---: | :--- | :--- |
| `langgraph_iteration_count` | Histogram | `domain`<br>Buckets: `1` → `15` | **Distribution of ReAct loops** per session before reaching final answer. Evaluates autonomous reasoning complexity. |
| `langgraph_forced_termination_total` | Counter | `domain`, `reason` (`max_iterations`, `budget_depleted`, `duplicate_action`, `max_rework_cycles`) | **Hard stop safeguard activations.** Ensures the agent never gets trapped in infinite execution loops, budget drains, or cyclic errors. |
| `langgraph_duplicate_tool_call_total` | Counter | `tool_name` | **Duplicate tool call detections (Action Tracker).** When an agent attempts to invoke the identical tool with identical parameters in a single session, the action is blocked to preserve tokens and time. |

---

## 4. Semantic Caching, Embeddings & Hybrid RAG

Declared in [`app/core/metrics.py`](../app/core/metrics.py).

| Metric Name | Type | Labels / Dimensions | Description & Significance |
| :--- | :---: | :--- | :--- |
| `semantic_cache_requests_total` | Counter | `status` (`hit`, `miss`, `error`) | **Total Semantic Cache lookups in Qdrant.** Used to compute Cache Hit Rate: $\frac{\text{hits}}{\text{total queries}}$. |
| `semantic_cache_duration_seconds` | Histogram | `operation` (`get`, `set`), `status` (`hit`, `miss`, `ok`, `error`)<br>Buckets: `0.005s` → `2.5s` | **Read/write duration for semantic cache**, including query embedding generation, ANN vector search in Qdrant, and cosine similarity filtering. |
| `agent_embedding_duration_seconds` | Histogram | `status` (`ok`, `error`)<br>Buckets: `0.005s` → `3.0s` | **Dense vector embedding latency** from embedding server (`Qwen3-Embedding-4B` or 9Router `text-embedding-3-small`). |
| `agent_rag_retrieval_duration_seconds` | Histogram | `collection`, `status` (`hit`, `empty`, `error`)<br>Buckets: `0.01s` → `3.0s` | **Hybrid retrieval latency in Qdrant**, combining dense vector ANN + sparse BM25 + Reciprocal Rank Fusion (RRF) re-ranking. |
| `agent_rag_retrieved_docs_count` | Histogram | `collection`<br>Buckets: `0` → `10` | **Number of relevant documents/hotels retrieved** after similarity threshold filtering. |

---

## 5. Token Governance & Cost Attribution

Declared in [`app/core/metrics.py`](../app/core/metrics.py).

| Metric Name | Type | Labels / Dimensions | Description & Significance |
| :--- | :---: | :--- | :--- |
| `agent_token_usage_total` | Counter | `tier` (`1`, `2`), `token_type` (`input`, `output`) | **Cumulative token consumption**, partitioned into input tokens (prompt + context) and output tokens (generated completion) per model tier. |
| `agent_estimated_cost_usd` | Histogram | Buckets: `$0.0001` → `$1.0` | **Estimated cost per LLM invocation (USD)** calculated according to model-specific pricing tables. |
| `agent_cost_per_tier_usd` | Histogram | `tier`<br>Buckets: `$0.0001` → `$0.1` | **Cost breakdown per model tier** (e.g., Tier 1 ultra-low-cost vs Tier 2 balanced reasoning). |
| `agent_node_input_tokens` | Histogram | `node_name`, `tier`<br>Buckets: `100` → `4096` | **Input token distribution per node.** Enforces bounds within context window ceilings (`max_context_tokens = 4096`). |
| `agent_node_output_tokens` | Histogram | `node_name`, `tier`<br>Buckets: `32` → `2048` | **Output token distribution per node.** Used to tune per-node generation limits (`NODE_MAX_TOKENS_*`). |
| `agent_node_output_truncated_total` | Counter | `node_name`, `tier` | **Instances where generation was truncated** due to reaching max completion limits (`finish_reason = length`). Flags constrained completion ceilings. |

---

## 6. Dynamic Complexity Routing

Declared in [`app/core/metrics.py`](../app/core/metrics.py).

| Metric Name | Type | Labels / Dimensions | Description & Significance |
| :--- | :---: | :--- | :--- |
| `agent_request_complexity_total` | Counter | `complexity` (`low`, `medium`, `high`), `intent_category` | **Request classification counts by complexity.** Measures proportion of lightweight lookups vs multi-step itineraries. |
| `agent_iterations_by_complexity` | Histogram | `complexity`<br>Buckets: `1` → `12` | **Actual graph loops executed** across request complexity tiers. |
| `agent_tool_calls_by_complexity` | Histogram | `complexity`<br>Buckets: `0` → `12` | **Tool call count distribution** across request complexity tiers. |
| `agent_rework_cycles_by_complexity` | Histogram | `complexity`<br>Buckets: `0` → `3` | **Critic rework cycle count** triggered due to deficiency before satisfying quality acceptance criteria. |
| `agent_soft_stop_trigger_total` | Counter | `node_name`, `reason` (`low_iterations`, `low_tools`, `rework`) | **Soft-stop prompt injections** advising the LLM to synthesize final output instead of spawning additional tool queries. |

---

## 7. vLLM Serving Engine Performance

Scraped directly from `/metrics` on the vLLM LLM Server (`Qwen/Qwen2.5-3B-Instruct-AWQ`) and Embedding Server (`Qwen/Qwen3-Embedding-4B`):

| Metric Name | Target / Filter | Description & Significance |
| :--- | :--- | :--- |
| `vllm:kv_cache_usage_perc` / `vllm:gpu_cache_usage_perc` | `instance="vllm-llm"` | **GPU KV Cache utilization percentage.** Warns of OOM or paging risk when approaching 100%. |
| `vllm:prefix_cache_hits_total` / `vllm:prefix_cache_queries_total` | `instance="vllm-llm"` | **Prefix cache hit and query totals.** Measures prompt cache reuse across recurring system prompts. |
| `vllm:num_requests_running` | `instance="vllm-llm"` / `vllm-embedding` | **Concurrent requests currently running on GPU.** |
| `vllm:num_requests_waiting` | `instance="vllm-llm"` | **Scheduler queue depth.** Requests waiting in queue due to GPU saturation. |
| `vllm:num_preemptions_total` | `instance="vllm-llm"` | **Request preemptions.** Frequency at which vLLM frees active requests due to KV cache exhaustion. |
| `vllm:prompt_tokens_total` | `instance="vllm-llm"` / `vllm-embedding` | **Input tokens ingested by GPU (Prefill stage).** Measures input token throughput (tokens/s). |
| `vllm:generation_tokens_total` | `instance="vllm-llm"` | **Output tokens produced by GPU (Decode stage).** Measures generation token throughput (tokens/s). |
| `vllm:time_to_first_token_seconds` | `instance="vllm-llm"` | **Engine-level TTFT** (excluding network transmission). |
| `vllm:inter_token_latency_seconds` / `vllm:time_per_output_token_seconds` | `instance="vllm-llm"` | **Inter-token latency (TPOT).** Dictates client streaming smoothness. |
| `vllm:e2e_request_latency_seconds` | `instance="vllm-llm"` / `vllm-embedding` | **Total end-to-end processing time inside the vLLM engine.** |
| `vllm:request_queue_time_seconds` | `instance="vllm-llm"` | **Waiting duration in scheduler queue before execution begins.** |
| `vllm:request_success_total` | `finished_reason` (`stop`, `length`) | **Successful request count**, grouped by completion reason (`stop` vs `length`). |
| `vllm:spec_decode_num_accepted_tokens_total` / `vllm:spec_decode_num_draft_tokens_total` | `instance="vllm-llm"` | **Speculative decoding acceptance ratio** when running draft model acceleration. |

---

## 8. k6 Distributed Load Testing Metrics

Configured in [`load_tests/travel_perf_test.js`](../load_tests/travel_perf_test.js) and [`load_tests/travel_grpc_perf_test.js`](../load_tests/travel_grpc_perf_test.js), exported to Prometheus via Remote Write:

| Metric Name | Type | Unit | Description & Significance |
| :--- | :---: | :---: | :--- |
| `travel_e2e_ms_all` / `travel_grpc_e2e_ms_all` | Trend | ms | Complete request/stream lifecycle duration across all complexity tiers. |
| `travel_ttft_ms_all` / `travel_grpc_ttft_ms_all` | Trend | ms | End-to-end Time to First Token perceived by client. |
| `travel_p95_sla_breaches` / `travel_grpc_p95_sla_breaches` | Counter | count | Count of requests breaching p95 SLA threshold (e.g., > 15s). |
| `travel_grpc_receipt_rate` | Rate | % | Percentage of gRPC streams containing a valid cryptographic ES256 response receipt. |
| `custom_errors` / `custom_grpc_errors` | Rate | % | Percentage of requests/streams failing or aborting during load tests. |
| `custom_sse_chunks_total` / `custom_grpc_chunks_total` | Counter | chunks | Total data token chunks successfully streamed to clients. |
