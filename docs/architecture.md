# 🏗️ Kiến Trúc Hệ Thống: Travel Assistant Agent

> **Phiên bản tài liệu**: 2026-11-11  
> **Nguồn**: `c:\Users\tuanm\OneDrive\project2\Booking\agent\`  
> **Stack**: Python · FastAPI · LangGraph · gRPC · Qdrant · RabbitMQ · Redis

---

## 📋 Mục lục

1. [Tổng quan hệ thống](#1-tổng-quan-hệ-thống)
2. [Sơ đồ kiến trúc tổng thể](#2-sơ-đồ-kiến-trúc-tổng-thể)
3. [Entry Points](#3-entry-points)
4. [gRPC Layer](#4-grpc-layer)
5. [API Layer (FastAPI)](#5-api-layer-fastapi)
6. [Bootstrap & DI Container](#6-bootstrap--di-container)
7. [Graph Workflow (LangGraph)](#7-graph-workflow-langgraph)
8. [Graph Nodes](#8-graph-nodes)
9. [Services Layer](#9-services-layer)
10. [Infrastructure Layer](#10-infrastructure-layer)
11. [MCP (Model Context Protocol)](#11-mcp-model-context-protocol)
12. [Core Utilities](#12-core-utilities)
13. [Interfaces (Abstractions)](#13-interfaces-abstractions)
14. [Retrieval Layer](#14-retrieval-layer)
15. [Background Tasks & Workers](#15-background-tasks--workers)
16. [gRPC Flow Thực Tế](#16-grpc-flow-thực-tế)
17. [Execution Flows Chi Tiết](#17-execution-flows-chi-tiết)

---

## 1. Tổng quan hệ thống

Hệ thống là một **Travel Assistant AI Agent** được xây dựng trên nền tảng:

| Thành phần | Công nghệ |
|---|---|
| AI Orchestration | LangGraph (Multi-node Workflow Graph) |
| gRPC Server | Python `grpc.aio` (async) — cổng 50051 |
| REST API | FastAPI — cổng 8000 |
| LLM Provider | 9Router / vLLM / Claude (pluggable) |
| Vector DB | Qdrant |
| Cache | Redis (Semantic Cache + Session) |
| Message Queue | RabbitMQ (AMQP) |
| Tool Framework | MCP (Model Context Protocol) via FastMCP |
| Monitoring | Prometheus + Grafana + OpenTelemetry |

Hệ thống hỗ trợ **hai mode hoạt động**:
- **`main.py`** — FastAPI REST server (HTTP)
- **`grpc_server.py`** — gRPC Streaming Server (gRPC bidirectional streaming)

---

## 2. Sơ đồ kiến trúc tổng thể

```
┌─────────────────────────────────────────────────────────────────┐
│                        CLIENT                                    │
│          (Frontend / External Service / Test Client)             │
└───────────┬────────────────────────┬────────────────────────────┘
            │ HTTP REST              │ gRPC (port 50051)
            ▼                        ▼
┌───────────────────┐    ┌───────────────────────────────────────┐
│  FastAPI REST API  │    │          gRPC Server (grpc.aio)        │
│  (port 8000)       │    │  ChatServiceServicer                   │
│  /api/v1/chat      │    │  - Chat() → ServerSideStreaming        │
│  /api/v1/config    │    │  AuthInterceptor (JWT middleware)      │
└────────┬──────────┘    └──────────────────┬────────────────────┘
         │                                   │
         ▼                                   ▼
┌──────────────────────────────────────────────────────────────────┐
│                   ChatStreamService                               │
│            app/services/streaming/chat_stream_service.py          │
│  - run_stream() / run_full() / run_langgraph()                    │
│  - Semantic Cache lookup → HybridRetriever → LangGraph            │
└───────────────────────────┬──────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────────┐
│               LangGraph Workflow Engine                           │
│               app/graph/workflow.py                               │
│                                                                   │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐  ┌───────────────┐  │
│  │Guardrail │→│  Planner  │→│  Executor  │→│  Synthesizer  │  │
│  └──────────┘  └──────────┘  └───────────┘  └───────────────┘  │
│                                    ↓                              │
│                              ┌──────────┐  ┌───────────────┐    │
│                              │Evaluator │→│OutputGuardrail│    │
│                              └──────────┘  └───────────────┘    │
└───────────────────────────────────────────────────────────────────┘
            │                       │                    │
            ▼                       ▼                    ▼
┌──────────────────┐  ┌───────────────────────┐  ┌────────────────┐
│   LLM Provider   │  │    Qdrant Vector DB    │  │  RabbitMQ MQ   │
│  (9Router/vLLM   │  │  - hotel_store         │  │  - shadow eval │
│   /Claude)       │  │  - memory_store        │  │  - llm tasks   │
│                  │  │  - semantic_cache       │  │                │
└──────────────────┘  └───────────────────────┘  └────────────────┘
            │
            ▼
┌──────────────────────────────────────────────────────────────────┐
│                   MCP Tool Layer                                  │
│               app/mcp/mcp_client.py                               │
│  - search_web() [DuckDuckGo]                                      │
│  - calculate_execution_time()                                     │
└──────────────────────────────────────────────────────────────────┘
```

---

## 3. Entry Points

### 📄 `app/main.py`
**Mục đích**: Khởi động FastAPI REST server

```python
# Chạy: uvicorn app.main:app --host 0.0.0.0 --port 8000
```

| Hàm | Tham số | Output | Mô tả |
|-----|---------|--------|-------|
| `lifespan(app)` | `app: FastAPI` | AsyncContextManager | Lifecycle handler: gọi `startup()` khi boot, cleanup khi tắt |

**Luồng khởi động**:
```
lifespan() 
  → startup()                   [bootstrap/startup.py]
  → container.initialize()      [bootstrap/container.py]
  → include_routers()           [api/router_registry.py]
  → app.include_router(chat_router)
  → app.include_router(config_router)
```

---

### 📄 `app/grpc_server.py`
**Mục đích**: Khởi động gRPC async server phục vụ streaming chat

| Hàm | Tham số | Output | Mô tả |
|-----|---------|--------|-------|
| `serve()` | — | None (async) | Khởi tạo gRPC server với interceptor, bind servicer |
| `ChatServiceServicer.Chat()` | `request_iterator`, `context` | `AsyncGenerator[ChatResponse]` | Handler chính nhận stream request, trả về stream response |

**Chi tiết `ChatServiceServicer.Chat()`**:
- Nhận `request_iterator` là async generator của `ChatRequest` protobuf
- Lấy `user_id`, `session_id`, `message`, `config_overrides` từ request đầu tiên
- Khởi tạo `ChatStreamService` từ DI container
- Gọi `chat_service.run_stream(...)` → yield từng `ChatResponse`
- Mỗi chunk được encode thành `ChatResponse(chunk=text, is_final=bool)`

**gRPC server configuration**:
```
Address:          0.0.0.0:50051
Max Workers:      10 thread pool
Interceptors:     [AuthInterceptor]
Compression:      gzip
Max Message Size: 100MB (send/receive)
```

---

### 📄 `app/worker_main.py`
**Mục đích**: Worker process độc lập chạy background tasks

| Hàm | Tham số | Output | Mô tả |
|-----|---------|--------|-------|
| `main()` | — | None (async) | Điểm vào chính của worker process |
| `start_all_workers()` | — | None | Khởi chạy tất cả worker consumers song song |
| `run_llm_worker()` | — | None | Chạy LLM task consumer từ RabbitMQ |
| `run_shadow_eval_worker()` | — | None | Chạy shadow evaluation worker |
| `run_hotel_sync_handler()` | — | None | Chạy hotel sync handler |
| `run_pruning_policy_worker()` | — | None | Chạy conversation pruning worker |

---

## 4. gRPC Layer

### 📄 `app/protos/chat.proto`
**Mục đích**: Định nghĩa gRPC service contract

```protobuf
service ChatService {
    rpc Chat(stream ChatRequest) returns (stream ChatResponse);
}

message ChatRequest {
    string user_id        = 1;
    string session_id     = 2;
    string message        = 3;
    string config_overrides = 4;  // JSON string
}

message ChatResponse {
    string chunk    = 1;
    bool   is_final = 2;
}
```

**Pattern**: Client-streaming → Server-streaming (bidirectional)

---

### 📄 `app/grpc_layer/auth_interceptor.py`
**Mục đích**: JWT authentication middleware cho gRPC

| Hàm/Class | Tham số | Output | Mô tả |
|-----------|---------|--------|-------|
| `AuthInterceptor` | — | — | gRPC ServerInterceptor |
| `intercept_service(continuation, handler_call_details)` | `continuation`, `handler_call_details` | gRPC handler | Validate JWT token trong metadata, reject nếu invalid |
| `_authenticate(metadata)` | `metadata: dict` | `bool` | Lấy `authorization` header, verify JWT |

**Flow xác thực**:
```
Client → gRPC call với header: authorization: Bearer <JWT>
       → AuthInterceptor.intercept_service()
         → _authenticate(metadata)
           → verify_jwt(token, settings.grpc_auth_secret)
             → Nếu valid: tiếp tục handle
             → Nếu invalid: abort(UNAUTHENTICATED)
```

---

### 📄 `app/grpc_layer/chat_pb2.py` & `chat_pb2_grpc.py`
**Mục đích**: Auto-generated protobuf stubs (từ `chat.proto`)

| Class | Mô tả |
|-------|-------|
| `ChatRequest` | Protobuf message: `user_id`, `session_id`, `message`, `config_overrides` |
| `ChatResponse` | Protobuf message: `chunk`, `is_final` |
| `ChatServiceStub` | Client stub để gọi gRPC |
| `ChatServiceServicer` | Base class cho server implementation |
| `add_ChatServiceServicer_to_server()` | Register servicer vào gRPC server |

---

## 5. API Layer (FastAPI)

### 📄 `app/api/router_registry.py`
**Mục đích**: Tập trung đăng ký tất cả API routers

| Hàm | Tham số | Output | Mô tả |
|-----|---------|--------|-------|
| `register_all_routers(app)` | `app: FastAPI` | None | Include tất cả sub-routers vào app |

**Danh sách routers đăng ký**:
- `/api/v1/chat` → `routes/chat.py`
- `/api/v1/config` → `routes/config.py`
- `/vision` → `routes/vision_demo.py`

---

### 📄 `app/api/routes/chat.py`
**Mục đích**: HTTP endpoints cho chat

| Endpoint | Method | Handler | Mô tả |
|----------|--------|---------|-------|
| `/api/v1/chat/stream` | POST | `chat_stream_endpoint()` | Streaming SSE response |
| `/api/v1/chat/sync` | POST | `chat_sync_endpoint()` | Blocking full response |

| Hàm | Tham số | Output | Mô tả |
|-----|---------|--------|-------|
| `chat_stream_endpoint(request, chat_service)` | `ChatRequest`, `ChatStreamService` | `StreamingResponse` | Server-Sent Events streaming |
| `chat_sync_endpoint(request, chat_service)` | `ChatRequest`, `ChatStreamService` | `JSONResponse` | Trả về full response một lần |

---

### 📄 `app/api/routes/config.py`
**Mục đích**: Endpoints quản lý runtime config

| Endpoint | Method | Mô tả |
|----------|--------|-------|
| `/api/v1/config/health` | GET | Health check endpoint |
| `/api/v1/config/metrics` | GET | Prometheus metrics dump |

---

### 📄 `app/api/auth.py`
**Mục đích**: HTTP Bearer token authentication

| Hàm | Tham số | Output | Mô tả |
|-----|---------|--------|-------|
| `get_current_user(token)` | `token: str` (from Bearer) | `dict` user payload | Verify JWT, raise 401 nếu invalid |

---

### 📄 `app/api/deps.py`
**Mục đích**: FastAPI dependency injection helpers

| Hàm | Tham số | Output | Mô tả |
|-----|---------|--------|-------|
| `get_chat_service()` | — | `ChatStreamService` | Lấy service từ DI container |
| `get_container()` | — | `AppContainer` | Trả về global container singleton |

---

### 📄 `app/api/routes/vision_demo.py`
**Mục đích**: Demo endpoints cho vision/multimodal (placeholder)

| Endpoint | Method | Mô tả |
|----------|--------|-------|
| `POST /vision/analyze` | POST | Nhận ảnh upload, trả về xác nhận (future: multi-modal LLM) |
| `POST /vision/detection` | POST | Object detection endpoint (future) |

---

## 6. Bootstrap & DI Container

### 📄 `app/bootstrap/container.py`
**Mục đích**: Dependency Injection container — khởi tạo và wire tất cả dependencies

```python
# Singleton pattern — global container
_container: AppContainer = None
```

| Hàm/Method | Tham số | Output | Mô tả |
|-----------|---------|--------|-------|
| `AppContainer.__init__()` | — | — | Khai báo tất cả dependency slots |
| `AppContainer.initialize()` | — | None (async) | Khởi tạo và wire tất cả dependencies |
| `get_container()` | — | `AppContainer` | Trả về global singleton |
| `initialize_container()` | — | `AppContainer` | Bootstrap lần đầu |

**Dependency graph trong container**:
```
AppContainer
├── settings                    [Settings]
├── embedding_provider          [EmbeddingProvider]
├── qdrant_vector_store         [QdrantVectorStore]
├── qdrant_hotel_store          [QdrantHotelStore]
├── qdrant_memory_store         [QdrantMemoryStore]
├── qdrant_cache                [QdrantSemanticCache]
├── hybrid_retriever            [HybridRetriever]
├── memory_service              [MemoryService]
├── fact_extractor              [FactExtractor]
├── query_transformer           [QueryTransformer]
├── mcp_client                  [MCPClient]
├── llm_queue_publisher         [LLMQueuePublisher]
├── rabbitmq_publisher          [RabbitMQPublisher]
├── job_result_store            [JobResultStore]
└── chat_stream_service         [ChatStreamService]
```

---

### 📄 `app/bootstrap/startup.py`
**Mục đích**: Điều phối startup sequence

| Hàm | Tham số | Output | Mô tả |
|-----|---------|--------|-------|
| `startup()` | — | None (async) | Gọi `initialize_container()`, setup logging, metrics |

---

### 📄 `app/bootstrap/health.py`
**Mục đích**: Health check logic

| Hàm | Tham số | Output | Mô tả |
|-----|---------|--------|-------|
| `get_health_status()` | — | `dict` | Kiểm tra kết nối Qdrant, Redis, RabbitMQ |
| `check_qdrant()` | — | `bool` | Ping Qdrant |
| `check_redis()` | — | `bool` | Ping Redis |
| `check_rabbitmq()` | — | `bool` | Test RabbitMQ connection |

---

## 7. Graph Workflow (LangGraph)

### 📄 `app/graph/workflow.py`
**Mục đích**: Định nghĩa LangGraph StateGraph — orchestration engine của agent

| Hàm | Tham số | Output | Mô tả |
|-----|---------|--------|-------|
| `build_graph()` | — | `CompiledStateGraph` | Compile và trả về LangGraph workflow |
| `get_compiled_graph()` | — | `CompiledStateGraph` | Singleton: build một lần, cache lại |

**Node registration trong graph**:

```python
graph.add_node("guardrail",       guardrail_node)
graph.add_node("planner",         planner_node)
graph.add_node("executor",        executor_node)
graph.add_node("evaluator",       evaluator_node)
graph.add_node("synthesizer",     synthesizer_node)
graph.add_node("output_guardrail",output_guardrail_node)
```

**Edge routing**:

```
START
  │
  ▼
guardrail ──[UNSAFE]──→ END (trả lỗi)
  │
  │[SAFE]
  ▼
planner
  │
  ▼
executor ──[TOOL_CALL]──→ executor (loop lại nếu còn tool calls)
  │
  │[DONE]
  ▼
evaluator
  │
  ├──[PASS]──→ output_guardrail ──→ synthesizer ──→ END
  │
  └──[RETRY]──→ planner (retry tối đa N lần)
```

---

### 📄 `app/graph/state.py`
**Mục đích**: Định nghĩa `AgentState` — shared state object đi qua tất cả nodes

```python
class AgentState(TypedDict):
    # === Input ===
    user_id:          str          # ID người dùng
    session_id:       str          # ID phiên chat
    messages:         List[BaseMessage]  # Lịch sử chat (LangChain messages)
    
    # === Config ===
    config:           RunnableConfig     # LangGraph config (thread_id, callbacks...)
    config_overrides: dict               # Runtime config overrides từ client
    
    # === Retrieval ===
    retrieved_docs:   List[str]          # Docs từ RAG retrieval
    hotel_results:    List[dict]         # Kết quả tìm kiếm khách sạn
    
    # === Planning ===
    plan:             dict               # Plan từ Planner node
    tool_calls:       List[dict]         # Tool calls được đề xuất
    tool_results:     List[dict]         # Kết quả từ tool execution
    
    # === Evaluation ===
    evaluation_score: float              # Score từ Evaluator (0.0-1.0)
    retry_count:      int                # Số lần retry
    
    # === Output ===
    final_response:   str               # Response cuối cùng cho user
    is_safe:          bool              # Guardrail result
    stream_chunks:    List[str]         # Chunks để stream
```

---

### 📄 `app/graph/schemas.py`
**Mục đích**: Pydantic models cho structured output từ LLM

| Schema | Fields | Mô tả |
|--------|--------|-------|
| `PlanOutput` | `steps: List[str]`, `tools_needed: List[str]`, `reasoning: str` | Output của Planner |
| `EvaluationOutput` | `score: float`, `passed: bool`, `feedback: str` | Output của Evaluator |
| `GuardrailOutput` | `is_safe: bool`, `reason: str` | Output của Guardrail |
| `ToolCall` | `tool_name: str`, `arguments: dict` | Một tool call |
| `ExecutorOutput` | `tool_calls: List[ToolCall]`, `direct_answer: str | None` | Output Executor |

---

### 📄 `app/graph/config.py`
**Mục đích**: LLM provider configuration và factory functions

| Hàm | Tham số | Output | Mô tả |
|-----|---------|--------|-------|
| `get_llm_instance(tier, config)` | `tier: int`, `config: dict` | `BaseChatModel` | Factory: trả về LLM instance theo tier và provider |
| `invoke_llm_with_limit(tier, llm, messages, config)` | `tier: int`, `llm`, `messages`, `config` | `(AIMessage, usage_dict)` | Invoke LLM với concurrency semaphore |
| `get_provider_config()` | — | `ProviderConfig` | Lấy config của provider hiện tại từ settings |

**LLM Tier System**:
```
Tier 1 (Fast/Cheap):  gpt-4o-mini / claude-3-5-haiku / vllm-fast
                      → Dùng cho: query transform, planning nhanh, guardrail
Tier 2 (Smart/Heavy): gpt-4o / claude-3-5-sonnet / vllm-full
                      → Dùng cho: synthesis, evaluation, complex reasoning
```

---

### 📄 `app/graph/utils.py`
**Mục đích**: Utility functions dùng trong graph nodes

| Hàm | Tham số | Output | Mô tả |
|-----|---------|--------|-------|
| `format_messages_for_llm(messages)` | `messages: List[BaseMessage]` | `List[BaseMessage]` | Format lịch sử cho LLM |
| `extract_latest_human_message(state)` | `state: AgentState` | `str` | Lấy tin nhắn mới nhất của user |
| `build_context_string(docs, hotels)` | `docs: List[str]`, `hotels: List[dict]` | `str` | Ghép retrieved context thành string |
| `truncate_messages(messages, max_tokens)` | `messages`, `max_tokens: int` | `List[BaseMessage]` | Cắt bớt messages khi quá dài |
| `count_tokens(text)` | `text: str` | `int` | Ước tính token count |

---

## 8. Graph Nodes

### 📄 `app/graph/nodes/__init__.py`
**Mục đích**: Export tất cả node functions

```python
from .guardrail       import guardrail_node
from .planner         import planner_node
from .executor        import executor_node
from .evaluator       import evaluator_node
from .synthesizer     import synthesizer_node
from .output_guardrail import output_guardrail_node
from .extractor       import extractor_node
```

---

### 📄 `app/graph/nodes/guardrail.py` — **Input Guardrail**
**Mục đích**: Kiểm tra input an toàn trước khi xử lý

| Hàm | Tham số | Output | Mô tả |
|-----|---------|--------|-------|
| `guardrail_node(state, config)` | `state: AgentState`, `config: RunnableConfig` | `AgentState` (updated) | Node function chạy input safety check |

**Flow nội bộ**:
```
guardrail_node()
  → Lấy latest human message từ state.messages
  → get_llm_instance(tier=1, config)       [config.py]
  → invoke_llm_with_limit(1, llm, prompt)
    → LLM phân loại: SAFE / UNSAFE
  → Cập nhật state.is_safe = True/False
  → Return state
```

**Prompt pattern**: Yêu cầu LLM phân loại tin nhắn có vi phạm content policy (harmful, illegal, hate speech...) hay không.

---

### 📄 `app/graph/nodes/planner.py` — **Task Planner**
**Mục đích**: Phân tích yêu cầu, lập kế hoạch các bước thực hiện

| Hàm | Tham số | Output | Mô tả |
|-----|---------|--------|-------|
| `planner_node(state, config)` | `state: AgentState`, `config: RunnableConfig` | `AgentState` (updated) | Lập kế hoạch xử lý request |

**Flow nội bộ**:
```
planner_node()
  → Lấy user message, lịch sử, retrieved_docs, hotel_results từ state
  → Xây dựng system prompt với context
  → get_llm_instance(tier=1, config)       [config.py]
  → invoke_llm_with_limit(1, llm, messages)
    → LLM output: PlanOutput (steps, tools_needed)
  → state.plan = plan_output
  → Return state
```

**Structured output**: `PlanOutput` với các fields: `steps`, `tools_needed`, `reasoning`

---

### 📄 `app/graph/nodes/executor.py` — **Tool Executor**
**Mục đích**: Thực thi tool calls theo kế hoạch của Planner

| Hàm | Tham số | Output | Mô tả |
|-----|---------|--------|-------|
| `executor_node(state, config)` | `state: AgentState`, `config: RunnableConfig` | `AgentState` (updated) | Thực thi tools, collect results |
| `_execute_tool(tool_name, arguments, mcp_client)` | `tool_name: str`, `arguments: dict`, `mcp_client` | `dict` | Gọi một tool cụ thể qua MCPClient |
| `_handle_hotel_search(query, state)` | `query: str`, `state` | `List[dict]` | Tìm kiếm khách sạn qua HybridRetriever |
| `_handle_web_search(query, mcp_client)` | `query: str`, `mcp_client` | `str` | Web search qua MCP tool |

**Flow nội bộ**:
```
executor_node()
  → Lấy plan.tools_needed từ state
  → Với mỗi tool call trong plan:
      → _execute_tool(tool_name, args, mcp_client)
        → Nếu "hotel_search":
            → HybridRetriever.search()     [retrieval/hybrid_retriever.py]
        → Nếu "web_search":
            → MCPClient.call_tool("search_web", query)
        → Nếu "calculate_time":
            → MCPClient.call_tool("calculate_execution_time", ms)
  → state.tool_results = [all results]
  → state.messages += [ToolMessage(result)]
  → Return state
```

---

### 📄 `app/graph/nodes/evaluator.py` — **Quality Evaluator**
**Mục đích**: Đánh giá chất lượng response trước khi trả về user

| Hàm | Tham số | Output | Mô tả |
|-----|---------|--------|-------|
| `evaluator_node(state, config)` | `state: AgentState`, `config: RunnableConfig` | `AgentState` (updated) | Chấm điểm quality của draft response |
| `_build_evaluation_prompt(state)` | `state: AgentState` | `List[BaseMessage]` | Xây dựng prompt đánh giá |
| `_should_retry(score, retry_count)` | `score: float`, `retry_count: int` | `bool` | Quyết định có retry không |

**Flow nội bộ**:
```
evaluator_node()
  → Lấy current draft response (từ tool_results hoặc synthesizer draft)
  → _build_evaluation_prompt(state)
  → get_llm_instance(tier=2, config)       [config.py — dùng Tier2 Smart LLM]
  → invoke_llm_with_limit(2, llm, eval_prompt)
    → LLM output: EvaluationOutput (score 0.0-1.0, passed, feedback)
  → state.evaluation_score = score
  → Nếu score < threshold VÀ retry_count < max_retry:
      → state.retry_count += 1
      → Route về planner (retry)
  → Nếu passed:
      → Route sang output_guardrail
```

**Publish shadow eval**: Sau mỗi lần evaluate, gửi message lên RabbitMQ cho shadow evaluation worker kiểm tra song song.

---

### 📄 `app/graph/nodes/synthesizer.py` — **Response Synthesizer**
**Mục đích**: Tổng hợp tất cả tool results thành response cuối cùng, có streaming

| Hàm | Tham số | Output | Mô tả |
|-----|---------|--------|-------|
| `synthesizer_node(state, config)` | `state: AgentState`, `config: RunnableConfig` | `AgentState` (updated) | Sinh response cuối |
| `_build_synthesis_prompt(state)` | `state: AgentState` | `List[BaseMessage]` | Ghép toàn bộ context vào prompt |

**Flow nội bộ**:
```
synthesizer_node()
  → _build_synthesis_prompt(state)
    → Ghép: lịch sử chat + retrieved_docs + hotel_results + tool_results
  → get_llm_instance(tier=2, config)       [Tier2 Smart LLM]
  → Streaming invoke: llm.astream(messages)
    → Yield từng token chunk
  → state.final_response = full_response
  → state.stream_chunks = [all chunks]
  → Return state
```

---

### 📄 `app/graph/nodes/extractor.py` — **Info Extractor**
**Mục đích**: Trích xuất thông tin có cấu trúc từ hội thoại

| Hàm | Tham số | Output | Mô tả |
|-----|---------|--------|-------|
| `extractor_node(state, config)` | `state: AgentState`, `config: RunnableConfig` | `AgentState` (updated) | Extract entities: dates, locations, preferences |
| `_extract_travel_info(message)` | `message: str` | `dict` | Extract travel-specific info |

---

### 📄 `app/graph/nodes/output_guardrail.py` — **Output Safety**
**Mục đích**: Kiểm tra output an toàn trước khi gửi cho user

| Hàm | Tham số | Output | Mô tả |
|-----|---------|--------|-------|
| `output_guardrail_node(state, config)` | `state: AgentState`, `config: RunnableConfig` | `AgentState` (updated) | Output safety check |

**Flow**: Tương tự input guardrail nhưng kiểm tra `state.final_response` thay vì input.

---

## 9. Services Layer

### 📄 `app/services/streaming/chat_stream_service.py`
**Mục đích**: Orchestrator chính điều phối toàn bộ chat flow

```python
class ChatStreamService:
    def __init__(self, container: AppContainer): ...
```

| Hàm | Tham số | Output | Mô tả |
|-----|---------|--------|-------|
| `run_stream(user_id, session_id, message, config_overrides)` | `str`, `str`, `str`, `dict` | `AsyncGenerator[str]` | Main streaming entry point |
| `run_full(user_id, session_id, message, config_overrides)` | `str`, `str`, `str`, `dict` | `str` | Blocking full response |
| `run_langgraph(state, config)` | `AgentState`, `RunnableConfig` | `AsyncGenerator[str]` | Chạy LangGraph workflow và stream output |
| `_check_semantic_cache(user_id, query)` | `str`, `str` | `str | None` | Tìm kiếm cache hit |
| `_save_to_cache(user_id, query, response)` | `str`, `str`, `str` | None | Lưu response vào semantic cache |
| `_load_session_history(user_id, session_id)` | `str`, `str` | `List[BaseMessage]` | Load chat history từ Redis |
| `_save_session_history(user_id, session_id, messages)` | `str`, `str`, `List[BaseMessage]` | None | Lưu chat history |
| `_retrieve_context(user_id, query)` | `str`, `str` | `tuple[List[str], List[dict]]` | RAG retrieval: docs + hotels |
| `_trigger_memory_update(user_id, messages)` | `str`, `List[BaseMessage]` | None | Trigger async memory update |
| `_build_initial_state(user_id, session_id, message, history, docs, hotels)` | — | `AgentState` | Xây dựng AgentState ban đầu |

**Flow hoàn chỉnh của `run_stream()`**:
```
run_stream(user_id, session_id, message, config_overrides)
  │
  ├─ 1. _load_session_history(user_id, session_id)
  │       → Redis GET session:{user_id}:{session_id}
  │
  ├─ 2. transform_user_query(message, history_summary)
  │       → LLM Tier1: "hotel in hanoi" → "hotels near Hoan Kiem Lake Hanoi Vietnam"
  │
  ├─ 3. _check_semantic_cache(user_id, optimized_query)
  │       → QdrantSemanticCache.lookup(query_embedding)
  │       → Nếu HIT: yield cached response → END
  │
  ├─ 4. _retrieve_context(user_id, optimized_query)
  │       → HybridRetriever.search(query)
  │         → BM25Search + VectorSearch → RRFSearch merge
  │         → Returns (docs, hotels)
  │
  ├─ 5. _build_initial_state(...)
  │       → AgentState với messages, retrieved_docs, hotel_results
  │
  ├─ 6. run_langgraph(state, config)
  │       → graph.astream_events(state, config)
  │         → guardrail_node
  │         → planner_node
  │         → executor_node (loop)
  │         → evaluator_node
  │         → output_guardrail_node
  │         → synthesizer_node  → yield chunks
  │
  ├─ 7. _save_to_cache(user_id, query, full_response)
  │
  ├─ 8. _save_session_history(user_id, session_id, updated_messages)
  │
  └─ 9. _trigger_memory_update(user_id, updated_messages)
          → fire-and-forget async task
          → MemoryWorker.process(messages)
            → FactExtractor.extract()
            → QdrantMemoryStore.add()
```

---

### 📄 `app/services/job_result_store.py`
**Mục đích**: Lưu kết quả async job vào Redis

```python
class JobResultStore:
    def __init__(self, redis_client): ...
```

| Hàm | Tham số | Output | Mô tả |
|-----|---------|--------|-------|
| `save(job_id, result, ttl)` | `str`, `dict`, `int=300` | None (async) | Lưu kết quả job vào Redis với TTL |
| `get(job_id)` | `str` | `dict | None` (async) | Lấy kết quả job |
| `delete(job_id)` | `str` | None (async) | Xóa job result |
| `exists(job_id)` | `str` | `bool` (async) | Kiểm tra job tồn tại |

---

### 📄 `app/services/memory_management/memory_service.py`
**Mục đích**: Facade service cho memory operations

```python
class MemoryService:
    def __init__(self, memory_store: QdrantMemoryStore, fact_extractor: FactExtractor): ...
```

| Hàm | Tham số | Output | Mô tả |
|-----|---------|--------|-------|
| `update_memory(user_id, messages)` | `str`, `List[BaseMessage]` | None (async) | Extract facts → store vào Qdrant |
| `retrieve_relevant_memory(user_id, query)` | `str`, `str` | `List[str]` (async) | Tìm kiếm long-term memory |
| `clear_user_memory(user_id)` | `str` | None (async) | Xóa toàn bộ memory của user |

---

### 📄 `app/services/memory_management/memory_worker.py`
**Mục đicht**: Background async worker xử lý memory updates

```python
class MemoryWorker:
    def __init__(self, memory_service: MemoryService): ...
```

| Hàm | Tham số | Output | Mô tả |
|-----|---------|--------|-------|
| `process(user_id, messages)` | `str`, `List[BaseMessage]` | None (async) | Gọi memory_service.update_memory() |
| `start()` | — | None (async) | Khởi động worker loop |

---

### 📄 `app/services/llm/fact_extractor.py`
**Mục đích**: Extract long-term facts từ hội thoại bằng LLM

```python
class FactExtractor:
    def __init__(self, llm_model): ...
```

| Hàm | Tham số | Output | Mô tả |
|-----|---------|--------|-------|
| `extract(chat_history_messages)` | `List[BaseMessage]` | `LongTermFacts | None` (async) | Phân tích 4 tin nhắn gần nhất, extract facts |

**Schemas**:
```python
class FactItem(BaseModel):
    category:         Literal["user_preference", "verified_knowledge", "system_constraint"]
    text:             str
    semantic_anchors: List[str]   # 3 câu query để tìm lại fact này
    importance:       float       # 0.0 - 1.0
    
class LongTermFacts(BaseModel):
    facts: List[FactItem]
```

**Strategy**: 
- Thử dùng `structured_output` trước
- Fallback sang JSON mode nếu model nhỏ (3B, 7B, mini)
- Fallback sang manual JSON parsing nếu structured output fail

---

### 📄 `app/services/llm/query_transformer.py`
**Mục đích**: Transform user query thành câu tìm kiếm tối ưu

| Hàm | Tham số | Output | Mô tả |
|-----|---------|--------|-------|
| `transform_user_query(latest_message, history_summary, config)` | `str`, `str`, `dict` | `str` (async) | LLM Tier1 rewrite query |

**Prompt**: "Convert to a single, clean, highly effective search query for vector search"

---

## 10. Infrastructure Layer

### 📄 `app/infrastructure/qdrant/qdrant_vector_store.py`
**Mục đích**: General-purpose vector store wrapper cho Qdrant

```python
class QdrantVectorStore(VectorStore):
    def __init__(self, client: QdrantClient, embedding_provider: EmbeddingProvider): ...
```

| Hàm | Tham số | Output | Mô tả |
|-----|---------|--------|-------|
| `add(collection_name, ids, embeddings, documents, metadatas)` | — | None (async) | Upsert vectors vào collection |
| `search(collection_name, embedding, top_k, filters)` | — | `List[dict]` (async) | Dense vector search |
| `hybrid_search(collection_name, query_text, dense_embedding, top_k, filters)` | — | `List[dict]` (async) | Sparse + Dense hybrid search |
| `delete(collection_name, ids)` | — | None (async) | Xóa vectors |
| `get(collection_name, filters)` | — | `List[dict]` (async) | Get by filter |
| `ensure_collection(collection_name, vector_size)` | `str`, `int` | None (async) | Tạo collection nếu chưa tồn tại |

---

### 📄 `app/infrastructure/qdrant/qdrant_hotel_store.py`
**Mục đích**: Domain-specific store cho hotel data

```python
class QdrantHotelStore:
    def __init__(self, vector_store: QdrantVectorStore): ...
    COLLECTION = "hotels"
```

| Hàm | Tham số | Output | Mô tả |
|-----|---------|--------|-------|
| `search_hotels(query_embedding, top_k, filters)` | `List[float]`, `int`, `dict` | `List[dict]` (async) | Tìm kiếm khách sạn theo vector similarity |
| `hybrid_search_hotels(query_text, dense_embedding, top_k, filters)` | — | `List[dict]` (async) | Hybrid search cho hotels |
| `add_hotel(hotel_id, embedding, hotel_data)` | `str`, `List[float]`, `dict` | None (async) | Thêm/cập nhật hotel |
| `delete_hotel(hotel_id)` | `str` | None (async) | Xóa hotel |
| `get_all_hotels(filters)` | `dict` | `List[dict]` (async) | Lấy danh sách hotels |

---

### 📄 `app/infrastructure/qdrant/qdrant_cache.py`
**Mục đích**: Semantic cache — tránh gọi LLM lại với query tương tự

```python
class QdrantSemanticCache(SemanticCache):
    COLLECTION = "semantic_cache"
    SIMILARITY_THRESHOLD = 0.92
```

| Hàm | Tham số | Output | Mô tả |
|-----|---------|--------|-------|
| `lookup(user_id, query_text, query_embedding)` | `str`, `str`, `List[float]` | `str | None` (async) | Tìm cache hit với cosine similarity ≥ 0.92 |
| `update(user_id, query_text, query_embedding, response)` | — | None (async) | Lưu response vào cache |
| `invalidate(user_id)` | `str` | None (async) | Xóa cache của user |
| `_is_expired(entry)` | `dict` | `bool` | Check TTL |

---

### 📄 `app/infrastructure/qdrant/qdrant_memory_store.py`
**Mục đích**: Long-term user memory store

```python
class QdrantMemoryStore(MemoryStore):
    COLLECTION = "user_memory"
```

| Hàm | Tham số | Output | Mô tả |
|-----|---------|--------|-------|
| `add(collection, doc_id, text, metadata)` | — | None (async) | Lưu memory fact |
| `get(collection, filters)` | — | `List[dict]` (async) | Lấy memories theo filter |
| `delete(collection, doc_id)` | — | None (async) | Xóa memory |

---

### 📄 `app/infrastructure/embedding_provider/embedding.py`
**Mục đích**: Provider embedding vectors (text → float[])

```python
class EmbeddingProvider(IEmbeddingProvider):
    def __init__(self, settings: Settings): ...
```

| Hàm | Tham số | Output | Mô tả |
|-----|---------|--------|-------|
| `embed(text)` | `str` | `List[float]` (async) | Tạo embedding vector cho một text |
| `embed_batch(texts)` | `List[str]` | `List[List[float]]` (async) | Batch embedding |

**Provider backends** (từ settings): FastEmbed / OpenAI Embeddings / Local

---

## 11. MCP (Model Context Protocol)

### 📄 `app/mcp/mcp_client.py`
**Mục đích**: Client giao tiếp với MCP server qua stdio

```python
class MCPClient:
    def __init__(self, config_path: str, jwt_secret: str): ...
```

| Hàm | Tham số | Output | Mô tả |
|-----|---------|--------|-------|
| `initialize()` | — | None (async) | Khởi động MCP server subprocess, thiết lập session |
| `call_tool(tool_name, arguments)` | `str`, `dict` | `Any` (async) | Gọi một MCP tool |
| `list_tools()` | — | `List[ToolDef]` (async) | Lấy danh sách tools available |
| `close()` | — | None (async) | Đóng MCP session, kill subprocess |
| `_generate_client_token()` | — | `str` | Sinh JWT token để authenticate với MCP server |

**Transport**: stdio (subprocess)  
**Security**: JWT HS256 handshake khi khởi động

---

### 📄 `app/mcp/server.py`
**Mục đích**: MCP server process (chạy độc lập qua stdio)

| Tool | Signature | Mô tả |
|------|-----------|-------|
| `calculate_execution_time(milliseconds)` | `int → str` | Chuyển ms → "X phút Y giây" |
| `search_web(query)` | `str → str` (async) | Web search với DuckDuckGo |

**Security**: Verify JWT token từ env `MCP_CLIENT_TOKEN` trước khi khởi động

---

### 📄 `app/mcp/tool_registry.py`
**Mục đích**: Registry quản lý available tools

| Hàm | Tham số | Output | Mô tả |
|-----|---------|--------|-------|
| `register_tool(name, handler)` | `str`, `Callable` | None | Đăng ký local tool |
| `get_tool(name)` | `str` | `Callable | None` | Lấy tool handler |
| `list_all_tools()` | — | `List[str]` | Liệt kê tất cả tools |

---

### 📄 `app/mcp/local_tools.py`
**Mục đích**: Local tool implementations (không qua MCP subprocess)

| Hàm | Tham số | Output | Mô tả |
|-----|---------|--------|-------|
| `get_current_datetime()` | — | `str` | Trả về datetime hiện tại |
| `format_currency(amount, currency)` | `float`, `str` | `str` | Format số tiền |

---

### 📄 `app/mcp/domains/web_tools.py`
**Mục đích**: Web search implementations

| Hàm | Tham số | Output | Mô tả |
|-----|---------|--------|-------|
| `search_web_logic(query)` | `str` | `str` (async) | DuckDuckGo search, format kết quả |
| `_format_results(results)` | `List[dict]` | `str` | Format search results thành text |

---

## 12. Core Utilities

### 📄 `app/core/settings.py`
**Mục đích**: Centralized configuration management (Pydantic Settings)

```python
class Settings(BaseSettings):
    # LLM
    llm_provider:        str    # "nine_router" | "vllm" | "claude"
    nine_router_api_key: SecretStr
    nine_router_base_url: str
    vllm_base_url:       str
    
    # Models
    tier1_model:         str    # "gpt-4o-mini"
    tier2_model:         str    # "gpt-4o"
    
    # Qdrant
    qdrant_url:          str
    qdrant_api_key:      SecretStr
    
    # Redis
    redis_url:           str
    
    # RabbitMQ
    rabbitmq_url:        str
    
    # Security
    grpc_auth_secret:    SecretStr  # JWT secret cho gRPC auth
    mcp_jwt_secret:      SecretStr  # JWT secret cho MCP auth
    
    # Security sub-model
    security: SecuritySettings
    
class SecuritySettings(BaseModel):
    redis_encryption_key:     SecretStr  # AES-256 key (base64)
    redis_encryption_old_key: SecretStr  # Key cũ cho key rotation
```

---

### 📄 `app/core/logger.py`
**Mục đích**: Structured logging setup

| Hàm | Tham số | Output | Mô tả |
|-----|---------|--------|-------|
| `setup_app_logger(name)` | `str` | `Logger` | Tạo logger với structlog/JSON format |
| `setup_root_logger()` | — | None | Configure root logger với handlers |
| `get_request_id()` | — | `str` | Lấy request ID từ context var |

**Format**: JSON structured logs với fields: `timestamp`, `level`, `name`, `message`, `request_id`, `user_id`

---

### 📄 `app/core/metrics.py`
**Mục đích**: Prometheus metrics definitions và helpers

| Metric | Type | Labels | Mô tả |
|--------|------|--------|-------|
| `llm_request_total` | Counter | `provider`, `model`, `tier` | Tổng số LLM requests |
| `llm_latency_seconds` | Histogram | `provider`, `model`, `tier` | LLM latency |
| `llm_token_cost_usd` | Counter | `provider`, `model` | Chi phí token USD |
| `cache_hit_total` | Counter | `type` | Cache hits (semantic, redis) |
| `grpc_request_total` | Counter | `method`, `status` | gRPC request count |
| `graph_node_duration_seconds` | Histogram | `node_name` | Time spent per graph node |
| `retrieval_duration_seconds` | Histogram | `type` | Retrieval latency |
| `active_sessions` | Gauge | — | Số sessions đang active |

| Hàm | Tham số | Output | Mô tả |
|-----|---------|--------|-------|
| `track_llm_call(provider, model, tier, latency, tokens, cost)` | — | None | Record LLM call metrics |
| `track_cache_hit(cache_type)` | `str` | None | Record cache hit |
| `track_graph_node(node_name, duration)` | `str`, `float` | None | Record node timing |

---

### 📄 `app/core/concurrency.py`
**Mục đích**: Global semaphores để giới hạn concurrent LLM calls

```python
# Per-provider limits:
TIER1_SEMAPHORE = asyncio.Semaphore(8)   # nine_router: 8
TIER2_SEMAPHORE = asyncio.Semaphore(8)   # nine_router: 8
#   vllm: tier1=24, tier2=24
#   claude: tier1=4, tier2=2
```

| Hàm | Tham số | Output | Mô tả |
|-----|---------|--------|-------|
| `get_semaphore(tier)` | `int` | `asyncio.Semaphore` | Lấy semaphore theo tier |

---

### 📄 `app/core/cost_model.py`
**Mục đích**: Token cost calculation per model

| Hàm | Tham số | Output | Mô tả |
|-----|---------|--------|-------|
| `get_token_cost(model_name, input_tokens, output_tokens)` | `str`, `int`, `int` | `tuple[float, float, float]` | Returns `(cost_in, cost_out, cost_total)` USD |
| `is_self_hosted(model_name)` | `str` | `bool` | True nếu là vLLM (không tính API cost) |

**Pricing table**:
```
gpt-4o-mini:                  $0.15/$0.60   per 1M tokens
gpt-4o:                       $5.00/$15.00  per 1M tokens
claude-3-5-haiku-20241022:    $0.80/$4.00   per 1M tokens
claude-3-5-sonnet-20241022:   $3.00/$15.00  per 1M tokens
vllm:                         $0.00/$0.00   (self-hosted)
```

---

### 📄 `app/core/helpers/crypto_helper.py`
**Mục đích**: AES-256-GCM encryption/decryption cho Redis data

| Hàm | Tham số | Output | Mô tả |
|-----|---------|--------|-------|
| `encrypt_value(plaintext)` | `str` | `str | None` | AES-256-GCM encrypt → base64(nonce+ciphertext+tag) |
| `decrypt_value(ciphertext_b64)` | `str` | `str | None` | Decrypt, thử cả primary key và old key (rotation) |
| `_get_active_keys()` | — | `List[bytes]` | Load + decode keys từ settings |

**Key rotation**: Hỗ trợ 2 keys (new + old) để seamless key rotation không downtime

---

### 📄 `app/core/helpers/jwt_helper.py`
**Mục đích**: JWT sign/verify (HS256)

| Hàm | Tham số | Output | Mô tả |
|-----|---------|--------|-------|
| `sign_jwt(payload, secret)` | `dict`, `str` | `str` | JWT encode HS256 |
| `verify_jwt(token, secret)` | `str`, `str` | `dict | None` | Decode và verify JWT |

---

### 📄 `app/core/helpers/asymmetric_helper.py`
**Mục đích**: ECDSA P-256 (ES256) asymmetric signing

| Hàm | Tham số | Output | Mô tả |
|-----|---------|--------|-------|
| `sign_data_es256(data, private_key_pem)` | `str`, `str` | `str` | ECDSA sign → base64 signature |
| `verify_data_es256(data, signature_b64, public_key_pem)` | `str`, `str`, `str` | `bool` | Verify ECDSA signature |

---

## 13. Interfaces (Abstractions)

### 📄 `app/interfaces/IVector_store.py`
```python
class VectorStore(ABC):
    async def add(collection_name, ids, embeddings, documents, metadatas)
    async def search(collection_name, embedding, top_k, filters)
    async def hybrid_search(collection_name, query_text, dense_embedding, top_k, filters)
    async def delete(collection_name, ids)
    async def get(collection_name, filters)
```

### 📄 `app/interfaces/IMemory_store.py`
```python
class MemoryStore(ABC):
    async def add(collection, doc_id, text, metadata)
    async def get(collection, filters)
    async def delete(collection, doc_id)
```

### 📄 `app/interfaces/ISemantic_cache.py`
```python
class SemanticCache(ABC):
    async def lookup(user_id, query_text, query_embedding) → str | None
    async def update(user_id, query_text, query_embedding, response)
    async def invalidate(user_id)
```

### 📄 `app/interfaces/IEmbedding_provider.py`
```python
class IEmbeddingProvider(ABC):
    async def embed(text: str) → List[float]
    async def embed_batch(texts: List[str]) → List[List[float]]
```

### 📄 `app/interfaces/IRetriever.py`
```python
class IRetriever(ABC):
    async def search(query: str, top_k: int, filters: dict) → List[dict]
```

---

## 14. Retrieval Layer

### 📄 `app/retrieval/hybrid_retriever.py`
**Mục đích**: Kết hợp BM25 + dense vector search với RRF fusion

```python
class HybridRetriever(IRetriever):
    def __init__(self, hotel_store: QdrantHotelStore, vector_store: QdrantVectorStore, 
                 embedding_provider: EmbeddingProvider): ...
```

| Hàm | Tham số | Output | Mô tả |
|-----|---------|--------|-------|
| `search(query, top_k, filters)` | `str`, `int`, `dict` | `tuple[List[str], List[dict]]` (async) | Hybrid search: docs + hotels |
| `_dense_search(query_embedding, top_k, filters)` | — | `List[dict]` | Qdrant dense vector search |
| `_sparse_search(query, top_k)` | — | `List[dict]` | BM25 keyword search |
| `_fuse_results(dense_results, sparse_results)` | — | `List[dict]` | RRF fusion và dedup |

---

### 📄 `app/retrieval/bm25_search.py`
**Mục đích**: BM25 keyword search trên local index

| Hàm | Tham số | Output | Mô tả |
|-----|---------|--------|-------|
| `BM25Search.__init__(corpus)` | `List[str]` | — | Build BM25 index từ corpus |
| `search(query, top_k)` | `str`, `int` | `List[tuple[int, float]]` | BM25 search, return (doc_idx, score) |

---

### 📄 `app/retrieval/rrf_search.py`
**Mục đích**: Reciprocal Rank Fusion để merge kết quả từ nhiều retrieval

| Hàm | Tham số | Output | Mô tả |
|-----|---------|--------|-------|
| `rrf_fusion(ranked_lists, k)` | `List[List[str]]`, `int=60` | `List[tuple[str, float]]` | RRF algorithm: score = Σ 1/(k + rank_i) |

**Formula**: 
$$\text{RRF}(d) = \sum_{r \in R} \frac{1}{k + r(d)}$$

---

## 15. Background Tasks & Workers

### 📄 `app/services/background_tasks/llm_worker.py`
**Mục đích**: Consumer xử lý async LLM jobs từ RabbitMQ

```python
class LLMWorker:
    QUEUE = "llm_tasks"
```

| Hàm | Tham số | Output | Mô tả |
|-----|---------|--------|-------|
| `start()` | — | None (async) | Bắt đầu consume từ queue `llm_tasks` |
| `_process_message(body)` | `bytes` | None (async) | Deserialize + xử lý LLM task |
| `_handle_completion_task(task)` | `dict` | None (async) | Thực thi LLM call, lưu kết quả |
| `stop()` | — | None | Graceful shutdown |

---

### 📄 `app/services/background_tasks/llm_queue_publisher.py`
**Mục đích**: Publish async LLM jobs lên RabbitMQ

```python
class LLMQueuePublisher:
    QUEUE = "llm_tasks"
```

| Hàm | Tham số | Output | Mô tả |
|-----|---------|--------|-------|
| `publish_task(task_type, payload)` | `str`, `dict` | `str` (async) | Publish job, return job_id |
| `publish_completion(session_id, messages)` | `str`, `List` | `str` (async) | Publish completion task |

---

### 📄 `app/services/background_tasks/rabbitmq_publisher.py`
**Mục đích**: Low-level RabbitMQ publisher

```python
class RabbitMQPublisher:
    def __init__(self, rabbitmq_url: str): ...
```

| Hàm | Tham số | Output | Mô tả |
|-----|---------|--------|-------|
| `connect()` | — | None (async) | Establish AMQP connection |
| `publish(exchange, routing_key, body, properties)` | `str`, `str`, `bytes`, `dict` | None (async) | Publish message |
| `close()` | — | None (async) | Close connection |
| `ensure_connected()` | — | None (async) | Reconnect nếu disconnected |

---

### 📄 `app/services/background_tasks/shadow_eval_worker.py`
**Mục đích**: Shadow evaluation — đánh giá response chất lượng offline

```python
class ShadowEvalWorker:
    QUEUE = "shadow_eval"
```

| Hàm | Tham số | Output | Mô tả |
|-----|---------|--------|-------|
| `start()` | — | None (async) | Consume từ queue `shadow_eval` |
| `_evaluate(session_id, user_query, response)` | `str`, `str`, `str` | None (async) | Chạy evaluation LLM, lưu metrics |
| `_save_eval_result(session_id, score, feedback)` | — | None (async) | Lưu kết quả vào Redis |

---

### 📄 `app/services/background_tasks/hotel_sync_handler.py`
**Mục đích**: Sync dữ liệu khách sạn từ external source vào Qdrant

```python
class HotelSyncHandler:
    QUEUE = "hotel_sync"
```

| Hàm | Tham số | Output | Mô tả |
|-----|---------|--------|-------|
| `start()` | — | None (async) | Consume sync events |
| `_sync_hotel(hotel_data)` | `dict` | None (async) | Embed hotel data → upsert vào Qdrant |
| `_delete_hotel(hotel_id)` | `str` | None (async) | Xóa hotel khỏi Qdrant |

---

### 📄 `app/services/background_tasks/pruning_policy.py`
**Mục đích**: Tự động cắt bớt conversation history khi quá dài

```python
class PruningPolicy:
    MAX_TOKENS = 8000
    KEEP_LAST_N = 10
```

| Hàm | Tham số | Output | Mô tả |
|-----|---------|--------|-------|
| `should_prune(messages)` | `List[BaseMessage]` | `bool` | Kiểm tra có cần prune không |
| `prune(messages)` | `List[BaseMessage]` | `List[BaseMessage]` | Giữ lại tin nhắn gần nhất, xóa cũ |
| `start()` | — | None (async) | Background pruning scheduler |

---

## 16. gRPC Flow Thực Tế

### 16.1 Luồng gRPC Chat Request → Response

```
CLIENT                    gRPC Server                   ChatStreamService              LangGraph
  │                           │                               │                           │
  │── ChatRequest(stream) ──→ │                               │                           │
  │   {user_id,              │                               │                           │
  │    session_id,           │                               │                           │
  │    message,              │                               │                           │
  │    config_overrides}     │                               │                           │
  │                          │                               │                           │
  │                          │── AuthInterceptor ──────────→│                           │
  │                          │   verify_jwt(token)           │                           │
  │                          │   ✓ AUTHENTICATED             │                           │
  │                          │                               │                           │
  │                          │── Chat(request_iter,ctx) ──→ │                           │
  │                          │                              ├─ _load_session_history()  │
  │                          │                              │   Redis GET session:*      │
  │                          │                              │                            │
  │                          │                              ├─ transform_user_query()   │
  │                          │                              │   LLM Tier1 rewrite        │
  │                          │                              │                            │
  │                          │                              ├─ _check_semantic_cache()  │
  │                          │                              │   Qdrant cosine lookup     │
  │                          │                              │                            │
  │                          │                              │  [CACHE HIT]               │
  │←─ ChatResponse(chunk) ───│←─ yield cached_response ────│                            │
  │   {chunk: "...",         │                              │                            │
  │    is_final: true}       │                              │  [CACHE MISS]              │
  │                          │                              ├─ _retrieve_context()       │
  │                          │                              │   HybridRetriever.search() │
  │                          │                              │   BM25 + Dense + RRF       │
  │                          │                              │                            │
  │                          │                              ├─ run_langgraph(state) ───→│
  │                          │                              │                           ├─ guardrail_node
  │                          │                              │                           │   LLM: SAFE/UNSAFE
  │                          │                              │                           │
  │                          │                              │                           ├─ planner_node
  │                          │                              │                           │   LLM: plan steps
  │                          │                              │                           │
  │                          │                              │                           ├─ executor_node
  │                          │                              │                           │   MCPClient.call_tool()
  │                          │                              │                           │   hotel_search
  │                          │                              │                           │
  │                          │                              │                           ├─ evaluator_node
  │                          │                              │                           │   LLM Tier2: score
  │                          │                              │                           │   publish shadow_eval
  │                          │                              │                           │
  │                          │                              │                           ├─ output_guardrail
  │                          │                              │                           │   LLM: output safe
  │                          │                              │                           │
  │                          │                              │                           └─ synthesizer_node
  │                          │                              │                               LLM Tier2 stream
  │                          │                              │←─ yield chunk1 ──────────────┤
  │←─ ChatResponse(chunk1) ──│←─ yield chunk1 ─────────────│                               │
  │   {chunk: "Xin chào",   │                              │←─ yield chunk2 ──────────────┤
  │    is_final: false}      │                              │                               │
  │                          │                              │                               ⋮
  │←─ ChatResponse(chunkN) ──│←─ yield chunkN ─────────────│←─ yield chunkN ──────────────┤
  │   {chunk: "...",         │                              │
  │    is_final: true}       │                              ├─ _save_to_cache()
  │                          │                              │   Qdrant upsert
  │                          │                              │
  │                          │                              ├─ _save_session_history()
  │                          │                              │   Redis SET session:*
  │                          │                              │
  │                          │                              └─ _trigger_memory_update()
  │                          │                                  fire-and-forget
  │                          │                                  FactExtractor → Qdrant
```

---

### 16.2 Luồng Background Worker

```
gRPC Server                RabbitMQ                   Workers
    │                         │                           │
    │── evaluator publishes ─→│── shadow_eval queue ──→  ShadowEvalWorker
    │   {session_id,          │                           │  _evaluate()
    │    query, response}     │                           │  LLM quality score
    │                         │                           │  → Redis save
    │                         │                           │
    │── hotel sync event ────→│── hotel_sync queue ───→  HotelSyncHandler
    │   {hotel_data}          │                           │  _sync_hotel()
    │                         │                           │  embed → Qdrant upsert
    │                         │                           │
    │── async llm task ──────→│── llm_tasks queue ────→  LLMWorker
    │   {task_type, payload}  │                           │  _process_message()
    │                         │                           │  LLM call → Redis save
```

---

## 17. Execution Flows Chi Tiết

### Flow 1: Người dùng hỏi "Khách sạn tốt ở Hội An?"

```
1. gRPC ChatRequest tới grpc_server.py
   ↓
2. AuthInterceptor verify JWT token
   ↓
3. ChatServiceServicer.Chat() khởi tạo ChatStreamService
   ↓
4. run_stream("user123", "sess456", "Khách sạn tốt ở Hội An?", {})
   ↓
5. Redis GET session:user123:sess456 → [] (phiên mới)
   ↓
6. QueryTransformer: "Khách sạn tốt ở Hội An?" 
   → LLM Tier1 →  "best hotels Hoi An Vietnam 4-star"
   ↓
7. QdrantSemanticCache.lookup(embedding("best hotels..."))
   → cosine similarity < 0.92 → CACHE MISS
   ↓
8. HybridRetriever.search("best hotels Hoi An Vietnam 4-star")
   → BM25Search("best hotels hoi an") → 20 keyword hits
   → EmbeddingProvider.embed(query) → [0.12, -0.34, ...]
   → QdrantHotelStore.hybrid_search(query_text, dense_embedding)
     → Qdrant sparse (BM25) + dense search
   → RRFSearch.rrf_fusion([bm25_results, dense_results])
   → Top 5 hotels: [{name: "Vinpearl", ...}, ...]
   ↓
9. AgentState khởi tạo:
   messages=[HumanMessage("Khách sạn tốt ở Hội An?")]
   hotel_results=[5 hotels]
   retrieved_docs=[relevant docs]
   ↓
10. LangGraph: graph.astream_events(state)
    ↓
    [guardrail_node]
    → LLM Tier1: "Câu hỏi về khách sạn → SAFE"
    → state.is_safe = True
    ↓
    [planner_node]
    → LLM Tier1: Lập kế hoạch
    → plan: {steps: ["search_hotels", "synthesize"], tools: ["hotel_search"]}
    ↓
    [executor_node]
    → hotel_search đã có trong state.hotel_results
    → Không cần call thêm MCP tools
    → state.tool_results = [{hotels_data}]
    ↓
    [evaluator_node]
    → LLM Tier2: đánh giá draft
    → score: 0.87 → PASS (threshold 0.70)
    → Publish to RabbitMQ shadow_eval queue
    ↓
    [output_guardrail_node]
    → LLM: response không có harmful content → SAFE
    ↓
    [synthesizer_node]
    → LLM Tier2 stream:
      "Dựa trên tìm kiếm, tôi đề xuất một số khách sạn tốt ở Hội An:
       1. **Vinpearl Resort** ..."
    → Mỗi token yield ra gRPC stream
   ↓
11. Full response assembled
    ↓
12. QdrantSemanticCache.update(query, embedding, full_response)
    ↓
13. Redis SET session:user123:sess456 = [updated_messages]
    ↓
14. fire-and-forget: MemoryWorker.process(messages)
    → FactExtractor.extract(last 4 messages)
      → LLM: "user_preference: 'thích khách sạn ở Hội An'"
    → QdrantMemoryStore.add("user_memory", doc_id, fact_text)
```

### Flow 2: Query tương tự → Semantic Cache Hit

```
1. User: "Có khách sạn nào đẹp ở Hội An không?"
   ↓
2. QueryTransformer → "hotels Hoi An Vietnam"
   ↓
3. QdrantSemanticCache.lookup(embed("hotels Hoi An Vietnam"))
   → cosine("hotels Hoi An Vietnam", "best hotels Hoi An Vietnam 4-star") = 0.94
   → 0.94 >= 0.92 → CACHE HIT!
   ↓
4. yield cached_response ngay lập tức
   → Tiết kiệm: không gọi LangGraph, không gọi LLM
   ↓
5. Chỉ gửi cache response về gRPC stream → is_final=true
```

### Flow 3: Worker xử lý Shadow Evaluation

```
RabbitMQ queue "shadow_eval"
   ↓
ShadowEvalWorker.start() [loop]
   ↓
_evaluate(session_id="sess456", 
          user_query="Khách sạn tốt ở Hội An?",
          response="Dựa trên tìm kiếm...")
   ↓
LLM Tier2 với rubric evaluation prompt:
  - Relevance score: 0.9
  - Accuracy score: 0.85
  - Completeness: 0.88
   ↓
_save_eval_result(session_id, avg_score=0.876, feedback="...")
  → Redis SET eval:sess456 = {score, feedback, timestamp}
   ↓
metrics.track_llm_call("shadow_eval", ...)
```

---

## 📁 File Tree Tổng Hợp

```
agent/
├── app/
│   ├── main.py                          # FastAPI app entry point
│   ├── grpc_server.py                   # gRPC server + ChatServiceServicer
│   ├── worker_main.py                   # Background worker process entry point
│   │
│   ├── api/
│   │   ├── auth.py                      # HTTP Bearer auth
│   │   ├── deps.py                      # FastAPI DI deps
│   │   ├── router_registry.py           # Router registration
│   │   └── routes/
│   │       ├── chat.py                  # /api/v1/chat endpoints
│   │       ├── config.py                # /api/v1/config endpoints
│   │       └── vision_demo.py           # /vision demo endpoints
│   │
│   ├── bootstrap/
│   │   ├── container.py                 # DI Container (all dependencies)
│   │   ├── health.py                    # Health check
│   │   └── startup.py                   # Startup sequence
│   │
│   ├── core/
│   │   ├── settings.py                  # Pydantic Settings (all config)
│   │   ├── logger.py                    # Structured logging
│   │   ├── metrics.py                   # Prometheus metrics
│   │   ├── concurrency.py               # Async semaphores per provider
│   │   ├── cost_model.py                # Token cost per model
│   │   └── helpers/
│   │       ├── crypto_helper.py         # AES-256-GCM encrypt/decrypt
│   │       ├── jwt_helper.py            # JWT HS256 sign/verify
│   │       └── asymmetric_helper.py     # ECDSA ES256 sign/verify
│   │
│   ├── graph/
│   │   ├── workflow.py                  # LangGraph StateGraph build
│   │   ├── state.py                     # AgentState TypedDict
│   │   ├── config.py                    # LLM factory + tier system
│   │   ├── schemas.py                   # Pydantic output schemas
│   │   ├── utils.py                     # Graph utility functions
│   │   └── nodes/
│   │       ├── __init__.py              # Node exports
│   │       ├── guardrail.py             # Input safety check node
│   │       ├── planner.py               # Task planning node
│   │       ├── executor.py              # Tool execution node
│   │       ├── evaluator.py             # Quality evaluation node
│   │       ├── synthesizer.py           # Response synthesis node
│   │       ├── output_guardrail.py      # Output safety check node
│   │       └── extractor.py             # Information extraction node
│   │
│   ├── grpc_layer/
│   │   ├── auth_interceptor.py          # gRPC JWT auth interceptor
│   │   ├── chat_pb2.py                  # Generated protobuf messages
│   │   └── chat_pb2_grpc.py             # Generated gRPC stubs
│   │
│   ├── infrastructure/
│   │   ├── embedding_provider/
│   │   │   └── embedding.py             # Text → vector embedding
│   │   └── qdrant/
│   │       ├── qdrant_vector_store.py   # General vector store
│   │       ├── qdrant_hotel_store.py    # Hotel domain store
│   │       ├── qdrant_cache.py          # Semantic cache (cosine ≥ 0.92)
│   │       └── qdrant_memory_store.py   # Long-term user memory
│   │
│   ├── interfaces/
│   │   ├── IVector_store.py             # ABC: add/search/delete/get
│   │   ├── IMemory_store.py             # ABC: add/get/delete
│   │   ├── ISemantic_cache.py           # ABC: lookup/update/invalidate
│   │   ├── IEmbedding_provider.py       # ABC: embed/embed_batch
│   │   └── IRetriever.py                # ABC: search
│   │
│   ├── mcp/
│   │   ├── server.py                    # FastMCP server (subprocess)
│   │   ├── mcp_client.py                # MCPClient (stdio transport)
│   │   ├── tool_registry.py             # Tool registry
│   │   ├── local_tools.py               # Local tools (no MCP)
│   │   ├── mcp_servers_config.json      # MCP server config
│   │   └── domains/
│   │       ├── core_tools.py            # calculate_execution_time
│   │       └── web_tools.py             # search_web (DuckDuckGo)
│   │
│   ├── retrieval/
│   │   ├── hybrid_retriever.py          # BM25 + Dense + RRF fusion
│   │   ├── bm25_search.py               # BM25 keyword search
│   │   └── rrf_search.py                # Reciprocal Rank Fusion
│   │
│   └── services/
│       ├── job_result_store.py          # Async job results (Redis)
│       ├── streaming/
│       │   └── chat_stream_service.py   # Main orchestrator service
│       ├── llm/
│       │   ├── fact_extractor.py        # LLM fact extraction
│       │   └── query_transformer.py     # Query optimization
│       ├── memory_management/
│       │   ├── memory_service.py        # Memory facade
│       │   └── memory_worker.py         # Async memory worker
│       ├── user/                        # (placeholder)
│       └── background_tasks/
│           ├── llm_worker.py            # RabbitMQ LLM task consumer
│           ├── llm_queue_publisher.py   # LLM task publisher
│           ├── rabbitmq_publisher.py    # Low-level AMQP publisher
│           ├── shadow_eval_worker.py    # Offline quality eval worker
│           ├── hotel_sync_handler.py    # Hotel data sync worker
│           └── pruning_policy.py        # Conversation pruning
│
├── protos/
│   └── chat.proto                       # gRPC service definition
│
├── serving/
│   ├── ollama/                          # Ollama serving config
│   └── vllm/                            # vLLM serving config
│
├── docker-compose.yml                   # Main stack (all services)
├── dockerfile                           # Agent container
├── prometheus.yml                       # Prometheus scrape config
└── langgraph.json                       # LangGraph Studio config
```

---

> **Ghi chú**: Tài liệu này được tổng hợp từ toàn bộ source code tại thời điểm 2026-11-11. Mọi thay đổi sau thời điểm này cần được cập nhật lại.
