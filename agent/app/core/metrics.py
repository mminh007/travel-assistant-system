# app/core/metrics.py
"""
Centralized Prometheus Metrics Registry.
Defines all observable parameters for Traffic, Latency, Token/Cost Governance,
RAG/Embedding Retrieval, Semantic Cache, and LangGraph Safeguards.
Allows separation of monitoring logic from core business operations.
"""
from prometheus_client import Counter, Gauge, Histogram

# ==========================================
# 1. TRAFFIC & END-TO-END STREAMING METRICS
# ==========================================
SSE_ACTIVE_STREAMS = Gauge(
    "sse_active_streams",
    "Number of concurrent active Server-Sent Event (SSE) HTTP streams",
)

SSE_DISCONNECT_TOTAL = Counter(
    "sse_disconnect_total",
    "Total number of closed SSE connections categorized by termination reason",
    ["reason"],  # "completed", "abrupt_client_disconnect", "cache_hit", "error"
)

GRPC_ACTIVE_STREAMS = Gauge(
    "grpc_active_streams",
    "Number of concurrent active gRPC chat streams currently processing",
)

GRPC_ERRORS_TOTAL = Counter(
    "grpc_errors_total",
    "Total number of gRPC runtime pipeline exceptions caught",
)

AGENT_REQUESTS_TOTAL = Counter(
    "agent_requests_total",
    "Total agent chat requests processed by transport protocol and outcome status",
    ["source", "status"],  # source=http|grpc, status=completed|cache_hit|error|cancelled
)

AGENT_REQUEST_DURATION_SECONDS = Histogram(
    "agent_request_duration_seconds",
    "End-to-end duration of agent chat requests in seconds",
    ["source", "status"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 3.5, 5.0, 7.5, 10.0, 15.0, 25.0, 40.0, 60.0),
)

AGENT_TTFT_SECONDS = Histogram(
    "agent_time_to_first_token_seconds",
    "User-perceived Time To First Token (seconds from request arrival to first streamed response chunk)",
    ["source", "cache_status"],  # cache_status=hit|miss
    buckets=(0.02, 0.05, 0.1, 0.2, 0.4, 0.75, 1.0, 1.5, 2.5, 4.0, 6.0, 10.0, 20.0),
)

# ==========================================
# 2. LANGGRAPH NODE & LLM EXECUTION METRICS
# ==========================================
NODE_DURATION_SECONDS = Histogram(
    "agent_node_duration_seconds",
    "Execution duration of individual LangGraph nodes in seconds",
    ["node_name"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 3.5, 5.0, 8.0, 12.0, 20.0),
)

LLM_CALL_DURATION_SECONDS = Histogram(
    "agent_llm_call_duration_seconds",
    "Duration of individual LLM inference calls (including semaphore wait) per node and tier",
    ["node_name", "tier", "status"],  # status=ok|truncated|error
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 1.5, 2.5, 4.0, 6.0, 10.0, 15.0, 30.0),
)

LLM_CALL_ERRORS_TOTAL = Counter(
    "agent_llm_call_errors_total",
    "Total LLM call failures categorized by node, tier, and exception type",
    ["node_name", "tier", "error_type"],
)

TOOL_CALL_DURATION_SECONDS = Histogram(
    "agent_tool_call_duration_seconds",
    "Execution duration of agent tools (MCP & local database tools) in seconds",
    ["tool_name", "status"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0),
)

# ==========================================
# 3. LANGGRAPH SAFEGUARDS & LOOP CONTROL
# ==========================================
GRAPH_ITERATIONS = Histogram(
    "langgraph_iteration_count",
    "Distribution of topological iterations (cycles) per graph execution session",
    ["domain"],
    buckets=(1, 2, 3, 4, 5, 6, 7, 8, 10, 15),
)

FORCED_TERMINATION_TOTAL = Counter(
    "langgraph_forced_termination_total",
    "Total occurrences where a procedural safeguard tripped and forced a hard termination",
    ["domain", "reason"],  # "max_iterations", "budget_depleted", "duplicate_action", "max_rework_cycles"
)

DUPLICATE_TOOL_CALL_TOTAL = Counter(
    "langgraph_duplicate_tool_call_total",
    "Total number of redundant tool invocations blocked by the action tracker mechanism",
    ["tool_name"],
)

# ==========================================
# 4. HYBRID RAG, EMBEDDING & SEMANTIC CACHE
# ==========================================
SEMANTIC_CACHE_LOOKUPS = Counter(
    "semantic_cache_requests_total",
    "Total semantic cache evaluation lookups categorized by resolution status",
    ["status"],  # "hit", "miss", "error"
)

SEMANTIC_CACHE_DURATION_SECONDS = Histogram(
    "semantic_cache_duration_seconds",
    "Latency of semantic cache lookup/store operations (embedding + Qdrant ANN + rerank)",
    ["operation", "status"],  # operation=get|set, status=hit|miss|ok|error
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5),
)

EMBEDDING_DURATION_SECONDS = Histogram(
    "agent_embedding_duration_seconds",
    "Latency of dense vector embedding calls to vLLM/upstream embedding server",
    ["status"],  # "ok", "error"
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.2, 0.4, 0.8, 1.5, 3.0),
)

RAG_RETRIEVAL_DURATION_SECONDS = Histogram(
    "agent_rag_retrieval_duration_seconds",
    "Latency of Qdrant hybrid retrieval (dense + BM25 sparse + RRF fusion)",
    ["collection", "status"],  # status=hit|empty|error
    buckets=(0.01, 0.025, 0.05, 0.1, 0.2, 0.4, 0.8, 1.5, 3.0),
)

RAG_RETRIEVED_DOCS = Histogram(
    "agent_rag_retrieved_docs_count",
    "Number of documents/hotels returned per RAG retrieval query",
    ["collection"],
    buckets=(0, 1, 2, 3, 5, 8, 10),
)

# ==========================================
# 5. COST TRACKING & TOKEN USAGE
# ==========================================
TOKEN_USAGE_COUNTER = Counter(
    "agent_token_usage_total",
    "Total token usage by tier and type",
    ["tier", "token_type"],  # tier=1|2, token_type=input|output
)

ESTIMATED_COST_GAUGE = Histogram(
    "agent_estimated_cost_usd",
    "Estimated USD cost per LLM invocation",
    buckets=[0.0001, 0.0005, 0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0],
)

COST_PER_TIER_HISTOGRAM = Histogram(
    "agent_cost_per_tier_usd",
    "Cost breakdown by LLM tier per invocation",
    ["tier"],
    buckets=[0.0001, 0.0005, 0.001, 0.005, 0.01, 0.05, 0.1],
)

# ==========================================
# 6. PER-NODE TOKEN GOVERNANCE METRICS
# ==========================================
NODE_INPUT_TOKENS = Histogram(
    "agent_node_input_tokens",
    "Distribution of input token counts per graph node (max_context_tokens=4096)",
    ["node_name", "tier"],
    buckets=(100, 250, 500, 800, 1200, 1600, 2048, 2800, 3500, 4096),
)

NODE_OUTPUT_TOKENS = Histogram(
    "agent_node_output_tokens",
    "Distribution of output token counts per graph node — used to calibrate max_tokens",
    ["node_name", "tier"],
    buckets=(32, 64, 128, 200, 300, 400, 600, 800, 1024, 1536, 2048),
)

NODE_TRUNCATION_TOTAL = Counter(
    "agent_node_output_truncated_total",
    "Total times a node's output was truncated (finish_reason=length)",
    ["node_name", "tier"],
)

# ==========================================
# 7. COMPLEXITY & LOOP CONTROL METRICS
# ==========================================
COMPLEXITY_DISTRIBUTION = Counter(
    "agent_request_complexity_total",
    "Number of requests per detected complexity level",
    ["complexity", "intent_category"],  # low | medium | high
)

ITERATIONS_BY_COMPLEXITY = Histogram(
    "agent_iterations_by_complexity",
    "Actual iteration count used per complexity level",
    ["complexity"],
    buckets=(1, 2, 3, 4, 5, 6, 7, 8, 10, 12),
)

TOOL_CALLS_BY_COMPLEXITY = Histogram(
    "agent_tool_calls_by_complexity",
    "Actual tool call count per complexity level",
    ["complexity"],
    buckets=(0, 1, 2, 3, 4, 5, 6, 7, 8, 10, 12),
)

REWORK_CYCLES_BY_COMPLEXITY = Histogram(
    "agent_rework_cycles_by_complexity",
    "Actual rework cycle count per complexity level",
    ["complexity"],
    buckets=(0, 1, 2, 3),
)

SOFT_STOP_TRIGGER_TOTAL = Counter(
    "agent_soft_stop_trigger_total",
    "Total times soft-stop warning was injected into a node's prompt",
    ["node_name", "reason"],  # reason: low_iterations | low_tools | rework
)
