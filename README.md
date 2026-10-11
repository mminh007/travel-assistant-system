# ✈️ Travel Assistant System

> A full-stack, AI-powered travel booking platform that pairs a production-grade **ASP.NET Core MVC** web application with a **multi-agent AI engine** built on LangGraph — now supporting **9Router** (managed multi-provider proxy) and **vLLM** (self-hosted GPU inference) as interchangeable LLM backends.

---

## 📑 Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [LLM Provider System](#llm-provider-system)
  - [9Router (Default)](#9router-default)
  - [vLLM Self-Hosted](#vllm-self-hosted)
  - [Switching Providers](#switching-providers)
- [Prerequisites](#prerequisites)
- [Getting Started](#getting-started)
  - [1. Clone the Repository](#1-clone-the-repository)
  - [2. Configure Environment Variables](#2-configure-environment-variables)
  - [3. Start 9Router](#3-start-9router)
  - [4. Run the Agent Engine](#4-run-the-agent-engine)
  - [5. Run the Website](#5-run-the-website)
- [vLLM Serving Configurations](#vllm-serving-configurations)
- [Agent Engine — Graph Architecture](#agent-engine--graph-architecture)
- [API Endpoints](#api-endpoints)
- [Infrastructure Services](#infrastructure-services)
- [Observability & Monitoring](#observability--monitoring)
- [Running Tests](#running-tests)
- [Contributing](#contributing)
- [License](#license)

---

## 🚀 Overview

The **Travel Assistant System** is a comprehensive intelligent travel booking platform. It allows users to search for flights and hotels, create bookings, process payments, and interact with an AI travel advisor — all through a unified web interface.

The system is composed of two independently deployable components:

| Component | Technology | Purpose |
|---|---|---|
| **Website** | ASP.NET Core MVC (.NET 10) | User-facing portal for browsing, booking, and payments |
| **Agent Engine** | Python · LangGraph · FastAPI | Multi-agent AI backend for travel planning and intelligent Q&A |

---

## 🛠️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Browser / Client                       │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│           Website  (ASP.NET Core MVC / .NET 10)             │
│  ┌──────────────┐  ┌────────────┐  ┌─────────────────────┐  │
│  │ Controllers  │  │  Services  │  │    SignalR Hub      │  │
│  │ (MVC + API)  │  │ Amadeus /  │  │     (ChatHub)       │  │
│  │              │  │  Stripe /  │  │                     │  │
│  │              │  │  Auth/JWT  │  │                     │  │
│  └──────┬───────┘  └────────────┘  └───────────┬─────────┘  │
│         │  SQL Server (EF Core)                │ gRPC       │
└─────────┼──────────────────────────────────────┼────────────┘
          │                                      │
┌─────────┼──────────────────────────────────────┼────────────┐
│         │    Agent Engine  (Python / Docker)   │            │
│  ┌──────▼────────────┐          ┌──────────────▼─────────┐  │
│  │ FastAPI REST API  │          │  gRPC Streaming Engine │  │
│  │   (port 8080)     │          │     (port 50051)       │  │
│  └──────────┬────────┘          └────────────────────────┘  │
│             │                                               │
│  ┌──────────▼───────────────────────────────────────────┐   │
│  │              LangGraph StateGraph                    │   │
│  │  Phase 0: input_guardrail → intent routing           │   │
│  │  Phase 1: planner | direct_executor_init             │   │
│  │  Phase 2: travel_react_agent (ReAct loop)            │   │
│  │  Phase 3: finding_extractor → fact_checker           │   │
│  │  Phase 4: evaluator_agent (rework loop)              │   │
│  │  Phase 5: task_manager → final_synthesizer           │   │
│  └──────────┬───────────────────────────────────────────┘   │
│             │                                               │
│  ┌──────────▼───────────────────────────────────────────┐   │
│  │               LLM Provider Layer                     │   │
│  │                                                      │   │
│  │  ┌─────────────────────┐  ┌──────────────────────┐   │   │
│  │  │   9Router Proxy     │  │   vLLM Self-Hosted   │   │   │
│  │  │   (port 20128)      │  │  (vast.ai / local)   │   │   │
│  │  │  OpenAI · Gemini    │  │  Qwen2.5-7B-Instruct │   │   │
│  │  │  Claude · LLaMA     │  │  + Qwen3-Embedding   │   │   │
│  │  │  DeepSeek           │  │                      │   │   │
│  │  └─────────────────────┘  └──────────────────────┘   │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │                  Infrastructure                      │   │
│  │  Redis · Qdrant · RabbitMQ · Prometheus / Grafana    │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## 🗝️ Tech Stack

### Website (Frontend + Backend)

| Layer | Technology |
|---|---|
| Framework | ASP.NET Core MVC (.NET 10) |
| ORM | Entity Framework Core 10 + SQL Server |
| Authentication | JWT Bearer tokens (cookie-based) |
| Payments | Stripe.net |
| Real-time | SignalR (`ChatHub`) |
| AI Integration | gRPC client (Grpc.Net.Client) |
| External APIs | Amadeus Travel API |
| Messaging | RabbitMQ.Client |

### Agent Engine (AI Backend)

| Layer | Technology |
|---|---|
| Runtime | Python 3.11+ |
| Web Framework | FastAPI + Uvicorn |
| AI Orchestration | LangGraph `StateGraph` |
| **LLM Gateway** | **9Router** (managed multi-provider proxy, port 20128) |
| **Self-Hosted LLM** | **vLLM** (Qwen2.5-7B-Instruct, AWQ/FP8 quantization) |
| Cloud LLM Providers | OpenAI · Anthropic Claude · Google Gemini · LLaMA · DeepSeek |
| Embedding | `text-embedding-3-small` (9Router) · `Qwen3-Embedding-4B` (vLLM) |
| Tool Protocol | MCP (Model Context Protocol) via `langchain-mcp-adapters` |
| Web Search | Tavily API |
| Vector Store | Qdrant (dense + BM25 hybrid retrieval) |
| Memory | Redis (session) + Qdrant (long-term) |
| Message Queue | RabbitMQ (async memory extraction worker) |
| Streaming API | gRPC (port 50051) |
| Observability | Prometheus · Grafana · Langfuse · Langsmith |
| Containerization | Docker + Docker Compose |

---

## 🔗 Project Structure

```
travel-assistant-system/
├── website/                          # ASP.NET Core MVC application
│   ├── Controllers/                  # MVC + API controllers
│   │   ├── AccountController.cs      # Auth (register/login/logout)
│   │   ├── BookingController.cs      # Booking CRUD
│   │   ├── FlightController.cs       # Flight search (Amadeus)
│   │   ├── HotelController.cs        # Hotel search & details
│   │   ├── PaymentController.cs      # Stripe payment flow
│   │   └── UserProfileController.cs  # User profile management
│   ├── Models/                       # EF Core domain models
│   ├── Views/                        # Razor views
│   ├── Services/                     # Business logic services
│   ├── Data/                         # DbContext + seeder
│   ├── Hubs/                         # SignalR ChatHub
│   ├── Middleware/                   # JWT, CORS, global exception handlers
│   ├── Protos/                       # gRPC .proto definitions
│   ├── Migrations/                   # EF Core database migrations
│   ├── appsettings.json
│   ├── Program.cs
│   └── Booking.Web.csproj
│
└── agent/                            # Python AI Agent Engine
    ├── app/
    │   ├── graph/                    # LangGraph workflow
    │   │   ├── workflow.py           # Graph factory (create_agent_graph)
    │   │   ├── nodes.py              # All agent nodes
    │   │   ├── state.py              # AgentState TypedDict
    │   │   ├── schemas.py            # Pydantic output schemas
    │   │   ├── config.py             # LLM factory & tiered instantiation
    │   │   └── utils.py              # Shared graph utilities
    │   ├── api/                      # FastAPI routers & auth
    │   │   ├── routes/
    │   │   │   ├── chat.py           # POST /chat/stream (SSE)
    │   │   │   ├── config.py         # POST /config/provider (per-user LLM config)
    │   │   │   └── vision_demo.py    # Vision demo endpoint
    │   │   ├── auth.py               # JWT authentication dependency
    │   │   └── router_registry.py    # Auto-discovery of FastAPI routers
    │   ├── core/                     # Settings, logger, metrics
    │   │   ├── settings.py           # Pydantic-based config (env-driven)
    │   │   │                         #   NineRouterSettings · VllmSettings · ...
    │   │   ├── logger.py             # Structured rotating-file logging
    │   │   └── metrics.py            # Prometheus metrics registry
    │   ├── mcp/                      # MCP tool definitions & client
    │   │   └── domains/              # Tool domains (web_search, core, travel)
    │   ├── infrastructure/           # Qdrant & embedding providers
    │   ├── services/                 # Memory, LLM, streaming, user services
    │   │   ├── streaming/
    │   │   │   └── chat_stream_service.py  # Core SSE stream + receipt signing
    │   │   └── llm/
    │   ├── grpc_layer/               # gRPC server & interceptors
    │   ├── grpc_server.py            # gRPC entry point (port 50051)
    │   ├── main.py                   # FastAPI app entry point (port 8080)
    │   └── worker_main.py            # RabbitMQ memory worker entry point
    │
    ├── serving/                      # Self-hosted model serving
    │   └── vllm/
    │       ├── configs/              # vLLM launch scripts (per optimization phase)
    │       │   ├── start_baseline.sh         # Baseline (no quantization)
    │       │   ├── start_awq.sh              # AWQ INT4
    │       │   ├── start_awq_chunked.sh      # AWQ + Chunked Prefill
    │       │   ├── start_awq_kv_fp8.sh       # AWQ + KV-Cache FP8
    │       │   ├── start_awq_prefix.sh       # AWQ + Prefix Caching
    │       │   └── start_spec_decoding.sh    # AWQ + Speculative Decoding
    │       ├── benchmarks/           # Benchmark results per config
    │       ├── results/              # Raw benchmark output
    │       └── test_connection.py    # vLLM connectivity test
    │
    ├── tests/unit/                   # Unit tests
    ├── load_tests/                   # k6 load test scripts
    ├── protos/                       # Shared gRPC .proto files
    ├── docs/                         # Additional documentation
    ├── docker-compose.yml            # Full stack deployment
    ├── docker-compose.9router.yml    # 9Router container
    ├── docker-compose.tracing.yml    # Tracing/observability stack
    ├── docker-compose.studio.yml     # LangGraph Studio dev mode
    ├── dockerfile
    ├── langgraph.json                # LangGraph Studio config
    ├── prometheus.yml
    └── requirements.txt
```

---

## 🤖 LLM Provider System

The agent engine supports two interchangeable LLM backends controlled by a single `LLM_PROVIDER` environment variable. The provider is resolved at startup; a process restart is required to switch.

### 9Router (Default)

**9Router** (`LLM_PROVIDER=nine_router`) is a self-hosted, OpenAI-compatible proxy that aggregates multiple cloud LLM providers under a single API key and endpoint.

```
┌──────────────────────────────────────────────────┐
│              9Router  (port 20128)               │
│  OpenAI-compatible endpoint: /v1                 │
│                                                  │
│  Routes requests to:                             │
│  • OpenAI   (GPT-4o, GPT-4o-mini, o1-mini)       │
│  • Anthropic (Claude 3.5 Sonnet, Haiku)          │
│  • Google    (Gemini 2.0 Flash/Pro)              │
│  • Meta      (LLaMA 3.1-8B / 3.3-70B / 405B)     │
│  • DeepSeek  (R1)                                │
└──────────────────────────────────────────────────┘
```

**Tiered model assignment:**

| Tier | Default Model | Nodes |
|---|---|---|
| **Tier 1** — Fast, ultra-low cost | `gpt-4o-mini` | `input_guardrail`, `clarification_agent`, `finding_extractor` |
| **Tier 2** — Balanced | `gpt-4o` | `planner`, `travel_react_agent`, `fact_checker`, `evaluator_agent`, `support_agent`, `final_synthesizer` |
| **Tier 3** — Reasoning | `o1-mini` | Reserved for high-complexity tasks |

### vLLM Self-Hosted

**vLLM** (`LLM_PROVIDER=vllm`) runs two concurrent processes on a GPU server (local or [vast.ai](https://vast.ai)):

| Process | Default Model | Port | Purpose |
|---|---|---|---|
| **LLM server** | `Qwen/Qwen2.5-7B-Instruct` | `8000` | Chat / reasoning inference |
| **Embedding server** | `Qwen/Qwen3-Embedding-4B` (2560 dims) | `8001` | Vector embeddings for Qdrant |

> ⚠️ **Port conflict note:** When using vLLM, the agent API server runs on **port 8080** (not 8000) to avoid colliding with the vLLM process.

Qdrant uses **dedicated collections** per provider to prevent embedding dimension mismatches:

| Provider | Memory Collection | Hotels Collection |
|---|---|---|
| 9Router | `long_term_memory` (1536 dims) | `hotels_collection` |
| vLLM | `long_term_memory_vllm` (2560 dims) | `hotels_collection_vllm` |

### Switching Providers

Edit `agent/.env` and restart the stack:

```env
# Use 9Router (default)
LLM_PROVIDER=nine_router

# Use vLLM self-hosted
LLM_PROVIDER=vllm
VLLM_BASE_URL=http://<host>:8000/v1
VLLM_MODEL=Qwen2.5-7B-Instruct-AWQ
```

Per-user provider overrides (with custom API keys) can also be submitted at runtime via `POST /config/provider`.

---

## ⚡ Prerequisites

### Website

- [.NET 10 SDK](https://dotnet.microsoft.com/download/dotnet/10.0)
- SQL Server (local or remote)
- Stripe account (for payment processing)
- Amadeus API credentials (for flight/hotel search)

### Agent Engine

- [Docker](https://www.docker.com/get-started) and [Docker Compose](https://docs.docker.com/compose/)
- **9Router** mode: API keys for at least one cloud provider (OpenAI, Anthropic, Gemini, etc.)
- **vLLM** mode: NVIDIA GPU with CUDA; vast.ai account (optional)
- Tavily API key (web search)

---

## ⚡ Getting Started

### 1. Clone the Repository

```bash
git clone https://github.com/mminh007/travel-assistant-system.git
cd travel-assistant-system
```

### 2. Configure Environment Variables

#### Agent Engine (`/agent/.env`)

```bash
cp agent/.env.example agent/.env
```

Key variables to configure:

```env
# ─── LLM Provider ───────────────────────────────────────────
LLM_PROVIDER=nine_router          # "nine_router" | "vllm"

# ─── 9Router ────────────────────────────────────────────────
NINE_ROUTER_BASE_URL=http://localhost:20128/v1
NINE_ROUTER_API_KEY=nine-router-key   # managed by 9Router

# Tier model overrides (optional — 9Router defaults shown)
NINE_ROUTER_TIER1_FAST_MODEL=gpt-4o-mini
NINE_ROUTER_TIER2_BALANCED_MODEL=gpt-4o
NINE_ROUTER_TIER3_REASONING_MODEL=o1-mini

# ─── Cloud provider keys (used by 9Router) ──────────────────
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=...
CLAUDE_API_KEY=sk-ant-...
LLAMA_API_KEY=...
DEEPSEEK_API_KEY=...

# ─── vLLM (only if LLM_PROVIDER=vllm) ──────────────────────
VLLM_BASE_URL=http://localhost:8000/v1
VLLM_MODEL=Qwen/Qwen2.5-7B-Instruct
VLLM_API_KEY=EMPTY

# ─── Web Search ─────────────────────────────────────────────
TAVILY_API_KEY=tvly-...

# ─── Infrastructure (auto-configured by Docker Compose) ─────
REDIS_URL=redis://redis_cache:6379/0
RABBITMQ_URL=amqp://guest:guest@rabbitmq_broker:5672/
QDRANT_SERVER_HOST=qdrant_server
QDRANT_SERVER_PORT=6333

# ─── Security — ECDSA keys for AI Response Receipts ─────────
SECURITY_AI_RECEIPT_PRIVATE_KEY=...
SECURITY_AI_RECEIPT_PUBLIC_KEY=...

# ─── MCP JWT Secret ─────────────────────────────────────────
MCP_JWT_SECRET=...

# ─── Observability (optional) ───────────────────────────────
LANGFUSE_SECRET_KEY=...
LANGFUSE_PUBLIC_KEY=...
LANGSMITH_API_KEY=...
```

#### Website (`/website/.env`)

```env
ConnectionStrings__DefaultConnection=Server=localhost;Database=TravelBooking;...
JwtSettings__SecretKey=...
JwtSettings__Issuer=TravelAssistant
JwtSettings__Audience=TravelAssistantUsers
StripeSettings__SecretKey=sk_test_...
```

### 3. Start 9Router

9Router runs in its own dedicated Docker Compose file. Start it first:

```bash
cd agent

# Create the shared Docker network (one-time setup)
docker network create agent_network

# Start 9Router
docker-compose -f docker-compose.9router.yml up -d

# Verify it is healthy
docker logs booking_9router
```

9Router will be available at `http://localhost:20128` with an OpenAI-compatible `/v1` endpoint. Add your cloud provider API keys through the 9Router dashboard, then configure your agents to use the 9Router endpoint.

### 4. Run the Agent Engine

```bash
cd agent

# Build and start all services
docker-compose up --build -d

# View logs
docker-compose logs -f
```

This starts the following containers:

| Container | Service | Port |
|---|---|---|
| `booking_9router` | 9Router API Proxy | `20128` |
| `booking_api_server` | FastAPI REST API | `8080` |
| `booking_grpc_server` | gRPC Streaming Engine | `50051` |
| `booking_memory_worker` | Async Memory Extraction Worker | — |
| `booking_redis` | Redis (session + checkpointing) | `6379` |
| `booking_rabbitmq` | RabbitMQ (message queue) | `5672`, `15672` |
| `booking_qdrant_server` | Qdrant (vector database) | `6333`, `6334` |
| `booking_prometheus` | Prometheus (metrics) | `9090` |
| `booking_grafana` | Grafana (dashboards) | `3001` |

> **Note:** The `k6_load_test` service is optional and only runs when you set the `K6_SCRIPT` environment variable.

### 5. Run the Website

Ensure the Agent Engine is running, then:

```bash
cd website

# Restore NuGet dependencies
dotnet restore

# Apply database migrations
dotnet ef database update

# Run the application
dotnet run
```

The website will be available at `https://localhost:5001` (or `http://localhost:5000`).

---

## 🌟 vLLM Serving Configurations

The `agent/serving/vllm/configs/` directory contains six optimized launch scripts for different GPU and latency profiles. All scripts target `Qwen/Qwen2.5-7B-Instruct` (or AWQ variant) by default and can be overridden via environment variables.

| Script | Strategy | Use Case |
|---|---|---|
| `start_baseline.sh` | No quantization | High VRAM, maximum quality |
| `start_awq.sh` | AWQ INT4 | Reduced VRAM, good quality |
| `start_awq_chunked.sh` | AWQ + Chunked Prefill | Reduced TTFT spike on long prompts |
| `start_awq_kv_fp8.sh` | AWQ + KV-Cache FP8 | Further VRAM reduction |
| `start_awq_prefix.sh` | AWQ + Prefix Caching | Repeated system prompts |
| `start_spec_decoding.sh` | AWQ + Speculative Decoding | Max throughput with draft model |

**Example — AWQ with Chunked Prefill:**

```bash
cd agent/serving/vllm
VLLM_MODEL=Qwen/Qwen2.5-7B-Instruct-AWQ bash configs/start_awq_chunked.sh
```

**Speculative Decoding** uses a draft model to accelerate token generation:

```bash
VLLM_MAIN_MODEL=Qwen/Qwen2.5-7B-Instruct-AWQ \
VLLM_DRAFT_MODEL=Qwen/Qwen2.5-1.5B-Instruct \
SPEC_TOKENS=5 \
bash configs/start_spec_decoding.sh
```

---

## 🧩 Agent Engine — Graph Architecture

The AI engine is a **6-phase directed graph** built with LangGraph. It uses a complexity-aware router to minimize LLM costs for simple queries while fully deploying the planning and evaluation pipeline for complex requests.

```
User Request
     │
     ▼
[Phase 0] input_guardrail (Tier 1 LLM)
     │
     ├─ Out of domain ──────────────────► out_of_domain → END
     ├─ Low confidence (< 0.70) ────────► clarification_agent → END
     ├─ FAQ / Navigation ────────────────► support_agent → END
     ├─ complexity = low ────────────────► direct_executor_init
     └─ complexity = medium/high ────────► planner
                                               │
[Phase 1]                                      │
planner (2-4 task decomposition)  ─────────────┤
direct_executor_init (1 synthetic task)  ───────┘
                                               │
                                               ▼
[Phase 2] travel_react_agent (ReAct Loop — Tier 2 LLM)
     │         ├─ action_tracker → tools (MCP) ──┐
     │         └───────────────────────────────-─┘
     │ (evaluate_tool_hooks: max 8 iterations, 10 tool calls)
     ▼
[Phase 3] finding_extractor (Tier 1) → fact_checker (Tier 2)

[Phase 4] evaluator_agent
     ├─ needs_rework=True (max 2 cycles) ──► travel_react_agent
     └─ needs_rework=False ───────────────► task_manager

[Phase 5] task_manager
     ├─ Tasks remaining ──────────────────► travel_react_agent (next task)
     └─ All done ─────────────────────────► final_synthesizer → END
```

### Programmatic Safeguards

| Safeguard | Constant | Action |
|---|---|---|
| Max ReAct iterations | `MAX_ITERATIONS = 8` | Force-route to `finding_extractor` |
| Max tool calls (budget) | `MAX_TOOL_CALLS = 10` | Force-route to `finding_extractor` |
| Duplicate tool detection | MD5 hash comparison | Block + force-route |
| Max rework cycles | `MAX_REWORK_CYCLES = 2` | Force-advance to `task_manager` |

### LLM Instance Caching

The LLM factory (`app/graph/config.py`) uses a **three-level cache** with collision-resistant keys that automatically invalidate on config or API key changes:

- `_LLM_INSTANCE_CACHE` — base `ChatOpenAI` instances per (provider, model, key)
- `_STRUCTURED_LLM_CACHE` — `.with_structured_output()` runnables per schema
- `_BOUND_LLM_CACHE` — tool-bound LLMs per MCP domain

---

## 🔌 API Endpoints

### Agent REST API (FastAPI — port 8080)

| Method | Path | Description |
|---|---|---|
| `POST` | `/chat/stream` | Send a message; returns a streaming SSE response with per-token chunks and a cryptographic receipt |
| `POST` | `/config/provider` | Submit per-user LLM provider config (custom key or system default) |
| `GET` | `/metrics` | Prometheus metrics scrape endpoint |

### Agent gRPC API (port 50051)

Defined in `protos/chat.proto`. The `AgentService` exposes a `Chat` server-streaming RPC for real-time token delivery to the ASP.NET website via gRPC.

### 9Router API (port 20128)

OpenAI-compatible proxy endpoint. Configure your cloud provider keys through the 9Router dashboard and use `/v1` as the base URL for any OpenAI-compatible client.

---

## 🔧 Infrastructure Services

| Service | URL | Default Credentials |
|---|---|---|
| FastAPI Docs (Swagger) | http://localhost:8080/docs | — |
| 9Router Dashboard | http://localhost:20128 | — |
| RabbitMQ Management | http://localhost:15672 | `guest` / `guest` |
| Qdrant Dashboard | http://localhost:6333/dashboard | — |
| Prometheus | http://localhost:9090 | — |
| Grafana | http://localhost:3001 | `admin` / `admin` |

> ⚠️ **Security:** Change all default credentials before deploying to a production environment.

---

## 📊 Observability & Monitoring

The agent engine ships with a complete observability stack:

- **Prometheus** — scrapes metrics exposed by `prometheus-client` at `/metrics`
- **Grafana** — pre-configured to pull from Prometheus; available at port `3001`
- **Langfuse / Langsmith** — optional LLM tracing (configure API keys in `.env`)
- **Structured Logging** — rotating log files written to `./logs/` (configurable via `LOGS_*` env vars)
- **AI Response Receipts** — every streamed response is ECDSA-signed (SECP256R1) for B2B integrity verification

To start the dedicated tracing stack:

```bash
docker-compose -f docker-compose.tracing.yml up -d
```

### Load Testing

k6 load test scripts are located in `agent/load_tests/`. Run a specific test script:

```bash
K6_SCRIPT=<script_filename>.js docker-compose up k6_load_test
```

---

## 🎮 Running Tests

### Agent Unit Tests

```bash
cd agent
pip install -r requirements.txt
pytest tests/unit/ -v
```

### gRPC Integration Test

```bash
cd agent
python test_grpc_receipt.py
```

### vLLM Connectivity Test

```bash
cd agent/serving/vllm
python test_connection.py
```

### Website

```bash
cd website
dotnet test
```

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature-name`
3. Commit your changes following [Conventional Commits](https://www.conventionalcommits.org/)
4. Push to your branch: `git push origin feature/your-feature-name`
5. Open a Pull Request

Please ensure all tests pass and new code is covered by unit tests before submitting a PR.

---

<p align="center">Built with ❤️ using LangGraph, ASP.NET Core, 9Router, vLLM, and modern AI tooling</p>
