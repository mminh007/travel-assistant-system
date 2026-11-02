# ✈️ Travel Assistant System

> A full-stack, AI-powered travel booking platform that pairs a production-grade **ASP.NET Core MVC** (.NET 10) web application with an autonomous **multi-agent AI engine** built on LangGraph — featuring interchangeable **9Router** (managed multi-provider cloud proxy) and **vLLM** (self-hosted GPU inference on local hardware or vast.ai) backends, hybrid RAG, semantic caching, and cryptographic response verification.

---

## 📑 Table of Contents

- [✈️ Travel Assistant System](#️-travel-assistant-system)
  - [📑 Table of Contents](#-table-of-contents)
  - [🚀 Overview](#-overview)
  - [🛠️ System Architecture](#️-system-architecture)
  - [✨ Key Features](#-key-features)
  - [📚 Core Documentation Index](#-core-documentation-index)
  - [🗝️ Tech Stack](#️-tech-stack)
    - [Website (Frontend \& Web Layer)](#website-frontend--web-layer)
    - [Agent Engine (AI \& Cognitive Layer)](#agent-engine-ai--cognitive-layer)
  - [🔗 Project Structure](#-project-structure)
  - [🤖 LLM Provider System](#-llm-provider-system)
    - [9Router (Managed Cloud Proxy)](#9router-managed-cloud-proxy)
    - [vLLM (Self-Hosted GPU Serving)](#vllm-self-hosted-gpu-serving)
    - [Switching Providers](#switching-providers)
  - [⚡ Prerequisites](#-prerequisites)
  - [🚀 Getting Started](#-getting-started)
    - [1. Clone Repository](#1-clone-repository)
    - [2. Environment Configuration](#2-environment-configuration)
      - [Configure Agent (`agent/.env`):](#configure-agent-agentenv)
      - [Configure Website (`website/.env`):](#configure-website-websiteenv)
    - [3. Start 9Router Gateway (If using 9Router)](#3-start-9router-gateway-if-using-9router)
    - [4. Start Agent Engine Stack](#4-start-agent-engine-stack)
    - [5. Run ASP.NET Core Website](#5-run-aspnet-core-website)
  - [🔧 Infrastructure \& Ports Directory](#-infrastructure--ports-directory)
  - [📊 Observability, Metrics \& Tracing](#-observability-metrics--tracing)
  - [🚀 Performance \& Load Testing](#-performance--load-testing)
  - [🧪 Running Automated Tests](#-running-automated-tests)
    - [Agent Unit Tests](#agent-unit-tests)
    - [gRPC Receipt Verification Test](#grpc-receipt-verification-test)
    - [vLLM Serving Connectivity Check](#vllm-serving-connectivity-check)
    - [ASP.NET Core Website Tests](#aspnet-core-website-tests)
  - [🔒 Security \& Verifiable AI Receipts](#-security--verifiable-ai-receipts)
  - [🤝 Contributing](#-contributing)
  - [📄 License](#-license)

---

## 🚀 Overview

The **Travel Assistant System** is a unified travel booking and advisory ecosystem. Users can search for flights and hotels, manage bookings, execute payments via Stripe, and interact with a streaming conversational AI travel advisor capable of building multi-day itineraries, finding accommodations, comparing flights, and answering travel policies.

The platform is engineered into two primary decoupled layers:
1. **User Portal (Website):** ASP.NET Core MVC (.NET 10) application managing authentication, SQL Server data persistence via EF Core, Stripe payments, Amadeus Travel API integration, and real-time streaming via SignalR `ChatHub`.
2. **Cognitive Agent Engine:** Python 3.11+ multi-agent backend powered by LangGraph, offering dual-transport streaming (HTTP SSE on port 8080 and gRPC on port 50051), Qdrant hybrid retrieval (Dense + BM25), semantic caching, and asynchronous RabbitMQ memory workers.

---

## 🛠️ System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                             Web Browser / Client                            │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ HTTP / WebSockets (SignalR)
┌──────────────────────────────────────▼──────────────────────────────────────┐
│                    Website  (ASP.NET Core MVC / .NET 10)                    │
│  ┌──────────────────┐  ┌──────────────────┐  ┌───────────────────────────┐  │
│  │ MVC Controllers  │  │ Domain Services  │  │   SignalR ChatHub         │  │
│  │ (Auth, Bookings, │  │ (Amadeus API,    │  │   (Real-time Token Stream │  │
│  │  Hotels, Flights)│  │  Stripe Payments)│  │    to Browser Clients)    │  │
│  └────────┬─────────┘  └──────────────────┘  └─────────────┬─────────────┘  │
│           │ SQL Server (EF Core)                           │ gRPC           │
└───────────┼────────────────────────────────────────────────┼────────────────┘
            │                                                │ (port 50051)
┌───────────┼────────────────────────────────────────────────┼────────────────┐
│           │            Agent Engine  (Python / Docker)     │                │
│  ┌────────▼──────────┐                          ┌──────────▼─────────────┐  │
│  │ FastAPI REST API  │                          │  gRPC Streaming Engine │  │
│  │ (SSE /chat/stream)│                          │  (AgentService.Chat)   │  │
│  │   (port 8080)     │                          │     (port 50051)       │  │
│  └────────┬──────────┘                          └──────────┬─────────────┘  │
│           │                                                │                │
│           └───────────────────────┬────────────────────────┘                │
│                                   │                                         │
│  ┌────────────────────────────────▼──────────────────────────────────────┐  │
│  │                    ChatStreamService Pipeline                         │  │
│  │  • Qdrant Semantic Cache Check (Instant TTFT < 50ms on Cache Hit)     │  │
│  │  • LangGraph StateGraph Execution (6-Phase Multi-Agent Graph)         │  │
│  │  • SECP256R1 Cryptographic AI Response Receipt Signing                │  │
│  │  • Async Memory Mining Task Dispatch to RabbitMQ                      │  │
│  └────────────────────────────────┬──────────────────────────────────────┘  │
│                                   │                                         │
│  ┌────────────────────────────────▼──────────────────────────────────────┐  │
│  │                       LangGraph StateGraph                            │  │
│  │  [Phase 0] input_guardrail → Complexity & Intent Classification       │  │
│  │  [Phase 1] planner (Multi-task) | direct_executor_init (Fast-path)    │  │
│  │  [Phase 2] travel_react_agent (ReAct Tool Loop + Action Tracker)      │  │
│  │  [Phase 3] finding_extractor (2-Phase Separation) → fact_checker      │  │
│  │  [Phase 4] evaluator_agent (Critic & Rework Gate, max 2 cycles)       │  │
│  │  [Phase 5] task_manager (Context Sandboxing) → final_synthesizer      │  │
│  └────────────────────────────────┬──────────────────────────────────────┘  │
│                                   │                                         │
│  ┌────────────────────────────────▼──────────────────────────────────────┐  │
│  │                        LLM Provider Layer                             │  │
│  │                                                                       │  │
│  │  ┌─────────────────────────────┐    ┌──────────────────────────────┐  │  │
│  │  │   9Router Managed Proxy     │    │   vLLM Self-Hosted Engine    │  │  │
│  │  │   (port 20128)              │    │   (vast.ai / Local GPU)      │  │  │
│  │  │   OpenAI · Anthropic Claude │    │   Qwen2.5-3B-Instruct-AWQ    │  │  │
│  │  │   Google Gemini · DeepSeek  │    │   + Qwen3-Embedding-4B       │  │  │
│  │  └─────────────────────────────┘    └──────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                   Supporting Infrastructure                           │  │
│  │  Redis (Sessions) · Qdrant (Hybrid RAG) · RabbitMQ (Worker Queue)     │  │
│  │  Prometheus (Metrics Scraping) · Grafana (Dashboards on port 3001)    │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## ✨ Key Features

* **Multi-Agent Orchestration with LangGraph:** 6-phase directed state graph featuring guardrail filtering, dynamic complexity-based routing, ReAct tool execution, and self-correcting evaluation loops.
* **Dual-Transport Streaming:** Unified `ChatStreamService` powering both HTTP SSE (`/chat/stream`) and high-performance server-streaming gRPC (`AgentService.StreamChat`).
* **Interchangeable LLM Providers:** Switch between **9Router** (OpenAI, Claude, Gemini, DeepSeek) and **vLLM** (self-hosted Qwen 2.5 on GPU) via a single environment variable (`LLM_PROVIDER`).
* **2-Phase Generation & Extraction Separation:** Executors generate free-form natural Markdown; a dedicated `finding_extractor` parses structured Pydantic schemas downstream, eliminating `JSONDecodeError` failures.
* **Deterministic Programmatic Safeguards:** Hard-coded guardrails enforce maximum iterations (`MAX_ITERATIONS = 8`), tool call budgets (`MAX_TOOL_CALLS = 10`), MD5-based duplicate action blocking, and capped rework cycles (`MAX_REWORK_CYCLES = 2`).
* **Strict Anti-Drift Language Matching:** Injected prompt constraints prevent local open-weights LLMs from drifting into Chinese tokens when analyzing multi-hop tool outputs.
* **Verifiable Response Provenance:** Every completed stream includes an ECDSA (SECP256R1) cryptographic **AI Response Receipt** signing the session ID, timestamp, and SHA-256 hash of the generated answer.
* **Hybrid RAG & Semantic Caching:** Qdrant vector database combining dense semantic embeddings with BM25 sparse search and Reciprocal Rank Fusion (RRF); semantic cache delivers instant responses with TTFT < 50ms.
* **Asynchronous Memory Mining:** Offloads user preference extraction and profile enrichment to a background RabbitMQ consumer pipeline (`MemoryWorker`), keeping chat latency low.
* **Comprehensive k6 Performance Suite:** Built-in load testing covering 10 to 1000 concurrent Virtual Users across both SSE and gRPC protocols with automated HTML/JSON reports and Grafana visualization.

---

## 📚 Core Documentation Index

For in-depth architectural and operational guides, consult the dedicated documentation files:

| Documentation                  | File Path                                                                                      | Focus Area                                                                                                           |
| ------------------------------ | ---------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| **Agent System Architecture**  | [`agent/README.md`](agent/README.md)                                                           | Exhaustive overview of LangGraph nodes, `AgentState`, safeguards, tiered LLM instantiation, and streaming internals. |
| **Metrics Tracking Reference** | [`agent/docs/metrics_tracking.md`](agent/docs/metrics_tracking.md)                             | Comprehensive dictionary of all Prometheus metrics (Traffic, TTFT, Nodes, Safeguards, Cache, Costs, vLLM, k6).       |
| **vLLM Deployment on vast.ai** | [`agent/docs/vast_setup_vllm.md`](agent/docs/vast_setup_vllm.md)                               | Step-by-step setup running concurrent LLM + Embedding servers on a single vast.ai RTX 3090 GPU (24GB VRAM).          |
| **Performance & Load Testing** | [`agent/docs/PERFORMANCE_TEST_GUIDE.md`](agent/docs/PERFORMANCE_TEST_GUIDE.md)                 | Detailed procedures and command lines for running k6 step-up, smoke, soak, spike, and complexity-isolated tests.     |
| **Structured Output Design**   | [`agent/docs/structured_output_design_guide.md`](agent/docs/structured_output_design_guide.md) | Architectural rationale for 2-phase generation/extraction separation and vLLM structured output handling.            |
| **Service Ports & Directory**  | [`agent/docs/api_document.md`](agent/docs/api_document.md)                                     | Complete directory of Docker Compose host ports, URLs, endpoints, and default service credentials.                   |
| **Master Agent Manifest**      | [`agent/workflow.md`](agent/workflow.md)                                                       | Master supervisor operational principles, intent taxonomy, and anti-drift language matching rules.                   |

---

## 🗝️ Tech Stack

### Website (Frontend & Web Layer)
* **Framework:** ASP.NET Core MVC (.NET 10)
* **ORM:** Entity Framework Core 10 + SQL Server
* **Real-time Streaming:** SignalR (`ChatHub`)
* **AI Integration:** gRPC client (`Grpc.Net.Client` referencing `Protos/chat.proto`)
* **Payments:** Stripe.net
* **Travel Data:** Amadeus Travel API
* **Security:** JWT Bearer authentication (HTTP-only secure cookies)

### Agent Engine (AI & Cognitive Layer)
* **Runtime:** Python 3.11+
* **Orchestration:** LangGraph `StateGraph`
* **Web & API Framework:** FastAPI + Uvicorn
* **gRPC Server:** `grpcio` + `grpcio-tools` (port 50051)
* **Cloud LLM Gateway:** **9Router** (OpenAI-compatible proxy, port 20128)
* **Self-Hosted Inference:** **vLLM** (`Qwen2.5-3B-Instruct-AWQ` + `Qwen3-Embedding-4B`)
* **Tool Calling Protocol:** Model Context Protocol (MCP) via `langchain-mcp-adapters`
* **Web Search:** Tavily API
* **Vector Store & Semantic Cache:** Qdrant (Dense + Sparse BM25 Hybrid Retrieval)
* **Session Store & Checkpointer:** Redis (`AsyncRedisSaver`)
* **Message Broker:** RabbitMQ (`aio-pika` / `pika`)
* **Observability:** Prometheus · Grafana · Langfuse · Langsmith
* **Load Testing:** k6 Distributed Runner

---

## 🔗 Project Structure

```
travel-assistant-system/
├── website/                                 # ASP.NET Core MVC Application (.NET 10)
│   ├── Controllers/                         # MVC & API controllers
│   │   ├── AccountController.cs             # Authentication & user sessions
│   │   ├── BookingController.cs             # Hotel & flight bookings
│   │   ├── FlightController.cs              # Flight search (Amadeus)
│   │   ├── HotelController.cs               # Hotel search & amenities
│   │   ├── PaymentController.cs             # Stripe checkout & webhooks
│   │   └── UserProfileController.cs         # Preferences & history
│   ├── Hubs/
│   │   └── ChatHub.cs                       # SignalR Hub streaming from gRPC agent
│   ├── Models/                              # EF Core entity models
│   ├── Views/                               # Razor Views (UI layout)
│   ├── Services/                            # Business logic & external API clients
│   ├── Middleware/                          # JWT, Correlation ID, Global Exception handlers
│   ├── Protos/                              # Shared gRPC protobuf definitions (chat.proto)
│   ├── Program.cs                           # App startup & dependency injection
│   └── Booking.Web.csproj
│
├── agent/                                   # Python Cognitive Agent Engine
│   ├── app/
│   │   ├── graph/                           # LangGraph multi-agent implementation
│   │   │   ├── nodes/                       # Modular graph node functions
│   │   │   │   ├── guardrail.py             # Phase 0: Input guardrail & routing
│   │   │   │   ├── planner.py               # Phase 1: Planner & direct init
│   │   │   │   ├── executor.py              # Phase 2: travel_react_agent, support, clarification
│   │   │   │   ├── extractor.py             # Phase 3: finding_extractor (2-phase)
│   │   │   │   ├── evaluator.py             # Phase 4: fact_checker & evaluator_agent
│   │   │   │   ├── synthesizer.py           # Phase 5: task_manager & final_synthesizer
│   │   │   │   └── __init__.py              # Public node exports
│   │   │   ├── workflow.py                  # StateGraph compiler & conditional routers
│   │   │   ├── state.py                     # AgentState TypedDict schema
│   │   │   ├── schemas.py                   # Pydantic schemas (ExecutorOutput, Findings)
│   │   │   ├── config.py                    # Tiered LLM factory, semaphores & 3-level caching
│   │   │   └── utils.py                     # Token cost tracking & manifest loader
│   │   ├── api/                             # FastAPI endpoints & route registry
│   │   │   ├── routes/                      # /chat/stream, /config/provider, etc.
│   │   │   └── auth.py                      # JWT verification dependencies
│   │   ├── grpc_layer/                      # Generated protobuf stubs & interceptors
│   │   ├── grpc_server.py                   # gRPC server entry point (port 50051)
│   │   ├── main.py                          # FastAPI application entry point (port 8080)
│   │   ├── worker_main.py                   # RabbitMQ background memory extraction worker
│   │   ├── services/
│   │   │   └── streaming/
│   │   │       └── chat_stream_service.py   # Unified SSE & gRPC streaming engine
│   │   ├── infrastructure/                  # Qdrant client, cache & hybrid retriever
│   │   ├── mcp/                             # Model Context Protocol tools & client
│   │   ├── core/                            # Pydantic settings, structured logger, metrics
│   │   └── bootstrap/                       # Container bootstrap & lifecycle events
│   │
│   ├── load_tests/                          # k6 Load Testing Suite
│   │   ├── travel_perf_test.js              # HTTP SSE load test script
│   │   ├── travel_grpc_perf_test.js         # gRPC streaming load test script
│   │   ├── questions_db.json                # 60 real travel questions (Low/Medium/High)
│   │   ├── export_system_metrics.py         # Unified 360° metrics exporter
│   │   └── reports/                         # Automated HTML and JSON reports
│   │
│   ├── serving/vllm/                        # Self-hosted vLLM configuration & benchmarks
│   │   ├── configs/                         # 6 GPU optimization launch scripts
│   │   └── test_connection.py               # Connectivity diagnostic script
│   │
│   ├── docs/                                # Technical Documentation
│   │   ├── api_document.md                  # Service ports & endpoints directory
│   │   ├── metrics_tracking.md              # Prometheus & Grafana metrics reference
│   │   ├── PERFORMANCE_TEST_GUIDE.md        # k6 load testing execution guide
│   │   ├── structured_output_design_guide.md# 2-phase structured output design guide
│   │   └── vast_setup_vllm.md               # vLLM deployment guide on vast.ai
│   │
│   ├── workflow.md                          # Master supervisor prompt manifest
│   ├── docker-compose.yml                   # Primary Docker stack
│   ├── docker-compose.9router.yml           # 9Router AI Gateway container
│   ├── docker-compose.tracing.yml           # Tracing stack (Langfuse)
│   ├── docker-compose.studio.yml            # LangGraph Studio dev environment
│   ├── prometheus.yml                       # Prometheus scrape targets
│   └── requirements.txt
│
├── AGENTS.md                                # GitNexus Codebase Intelligence Index
└── README.md                                # Project Root Documentation
```

---

## 🤖 LLM Provider System

The agent engine supports two interchangeable LLM backends controlled by the `LLM_PROVIDER` environment variable in `agent/.env`.

### 9Router (Managed Cloud Proxy)

Set `LLM_PROVIDER=nine_router` to route through a local or remote 9Router instance (`port 20128`), proxying requests to commercial cloud APIs under unified billing:

| Model Tier                      | Default Model | Node Workloads                                                                          |
| ------------------------------- | ------------- | --------------------------------------------------------------------------------------- |
| **Tier 1 (Fast & Low-Cost)**    | `gpt-4o-mini` | `input_guardrail`, `finding_extractor`, `clarification_agent`                           |
| **Tier 2 (Balanced Reasoning)** | `gpt-4o`      | `planner`, `travel_react_agent`, `fact_checker`, `evaluator_agent`, `final_synthesizer` |
| **Tier 3 (Deep Reasoning)**     | `o1-mini`     | Complex optimization and algorithmic travel planning                                    |

### vLLM (Self-Hosted GPU Serving)

Set `LLM_PROVIDER=vllm` to route requests to an OpenAI-compatible vLLM serving instance running locally or on [vast.ai](https://vast.ai):

| Server               | Model                          | Target Port | Context Length | Role                                                 |
| -------------------- | ------------------------------ | ----------- | -------------- | ---------------------------------------------------- |
| **LLM Server**       | `Qwen/Qwen2.5-3B-Instruct-AWQ` | `8000`      | 4096           | Reasoning, planning, extraction & synthesis          |
| **Embedding Server** | `Qwen/Qwen3-Embedding-4B`      | `10100`     | 4096           | Dense vector embeddings for Qdrant (2560 dimensions) |

> ℹ️ Qdrant automatically uses dedicated collections (`long_term_memory_vllm` and `hotels_collection_vllm`) when running in vLLM mode to maintain dimension isolation. For a complete guide to deploying on vast.ai with an RTX 3090, see [`agent/docs/vast_setup_vllm.md`](agent/docs/vast_setup_vllm.md).

### Switching Providers

Edit `agent/.env`:
```env
# Option A: 9Router Proxy (Default)
LLM_PROVIDER=nine_router
NINE_ROUTER_BASE_URL=http://localhost:20128/v1
NINE_ROUTER_API_KEY=nine-router-key

# Option B: vLLM Self-Hosted
LLM_PROVIDER=vllm
VLLM_BASE_URL=http://localhost:8000/v1
VLLM_MODEL=Qwen2.5-3B-Instruct-AWQ
VLLM_API_KEY=EMPTY
```

---

## ⚡ Prerequisites

* **Operating System:** Windows, Linux, or macOS
* **Containerization:** [Docker Desktop](https://www.docker.com/products/docker-desktop/) with Docker Compose v2+
* **Web Portal:** [.NET 10 SDK](https://dotnet.microsoft.com/download/dotnet/10.0) + SQL Server
* **Python Runtime (for local development/testing):** Python 3.11+
* **API Keys:**
  * At least one commercial LLM key (OpenAI, Anthropic, Gemini) if using 9Router
  * [Tavily Search API Key](https://tavily.com/) (for web research tools)
  * [Stripe](https://stripe.com/) test keys (for booking checkout)
  * [Amadeus](https://developers.amadeus.com/) API credentials (for flight & hotel search)

---

## 🚀 Getting Started

### 1. Clone Repository

```bash
git clone https://github.com/mminh007/travel-assistant-system.git
cd travel-assistant-system
```

### 2. Environment Configuration

#### Configure Agent (`agent/.env`):
```bash
cd agent
cp .env.example .env
```
Fill in the required secrets (API keys, ECDSA receipt keys, MCP secret).

#### Configure Website (`website/.env`):
```bash
cd ../website
```
Create `website/.env` with your SQL Server connection string, JWT secret, and Stripe keys:
```env
ConnectionStrings__DefaultConnection=Server=localhost;Database=TravelBooking;Trusted_Connection=True;TrustServerCertificate=True;
JwtSettings__SecretKey=YourSuperSecretKeyWithAtLeast32CharactersLong!
JwtSettings__Issuer=TravelAssistant
JwtSettings__Audience=TravelAssistantUsers
StripeSettings__SecretKey=sk_test_...
```

### 3. Start 9Router Gateway (If using 9Router)

If using 9Router as your LLM gateway, initialize the shared network and launch the 9Router container:

```bash
cd ../agent

# Create shared Docker bridge network (run once)
docker network create agent_network

# Start 9Router
docker-compose -f docker-compose.9router.yml up -d
```
Access the 9Router dashboard at `http://localhost:20128` to register your cloud provider API keys.

### 4. Start Agent Engine Stack

From the `agent` directory:

```bash
cd agent
docker compose up -d --build
```

Verify that all core containers are healthy:
```bash
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

### 5. Run ASP.NET Core Website

In a new terminal window:

```bash
cd website

# Restore dependencies
dotnet restore

# Run database migrations and seed data
dotnet ef database update

# Run web application
dotnet run
```
Navigate to `https://localhost:5001` or `http://localhost:5000` to access the travel booking portal.

---

## 🔧 Infrastructure & Ports Directory

| Service                | Container Name          | Exposed Host Port / URL                                                      | Default Credentials | Description                                 |
| ---------------------- | ----------------------- | ---------------------------------------------------------------------------- | ------------------- | ------------------------------------------- |
| **FastAPI REST & SSE** | `booking_api_server`    | [http://localhost:8080](http://localhost:8080)<br>Swagger: `/docs`           | —                   | HTTP SSE streaming and REST endpoints       |
| **Agent gRPC Engine**  | `booking_grpc_server`   | `localhost:50051`<br>Metrics: [http://localhost:8002](http://localhost:8002) | —                   | Binary streaming engine consumed by SignalR |
| **Prometheus**         | `booking_prometheus`    | [http://localhost:9090](http://localhost:9090)                               | —                   | Scrapes metrics from agent, gRPC, and vLLM  |
| **Grafana**            | `booking_grafana`       | [http://localhost:3001](http://localhost:3001)                               | `admin` / `admin`   | Real-time monitoring dashboards             |
| **Qdrant Vector DB**   | `booking_qdrant_server` | [http://localhost:6333/dashboard](http://localhost:6333/dashboard)           | —                   | Hybrid vector store and semantic cache      |
| **RabbitMQ Broker**    | `booking_rabbitmq`      | [http://localhost:15672](http://localhost:15672)<br>AMQP: `5672`             | `guest` / `guest`   | Async memory extraction task queue          |
| **Redis Cache**        | `booking_redis`         | `localhost:6379`                                                             | —                   | Session store and LangGraph checkpointer    |
| **9Router Proxy**      | `booking_9router`       | [http://localhost:20128](http://localhost:20128)                             | —                   | Multi-cloud model routing gateway           |

For complete connection and configuration guidance, see [`agent/docs/api_document.md`](agent/docs/api_document.md).

---

## 📊 Observability, Metrics & Tracing

The stack includes comprehensive Prometheus instrumentation across 8 dimensions:
1. **Streaming Traffic & E2E Latency:** Active SSE/gRPC streams, TTFT, request rates.
2. **LangGraph Execution:** Per-node durations, LLM invocation latency, error counts.
3. **Safeguards & ReAct Cycles:** Loop distributions, forced terminations, duplicate tool catches.
4. **Hybrid RAG & Semantic Caching:** Qdrant latency, cache hit ratios, retrieval volume.
5. **Token Governance & Cost Attribution:** Input/output token counters, dollar cost estimates.
6. **Complexity Profiling:** Distribution of low/medium/high queries and tool calls.
7. **vLLM Engine Health:** GPU KV cache usage %, scheduler waiting queues, tokens/sec.
8. **k6 Benchmark Metrics:** Client-side percentiles (P50, P95), SLA breach counters.

For full schema details, see [`agent/docs/metrics_tracking.md`](agent/docs/metrics_tracking.md).

---

## 🚀 Performance & Load Testing

The platform includes a turn-key k6 load testing suite in `agent/load_tests/` with 60 categorized travel questions (`questions_db.json`).

Run standard staircase step-up load tests (10 → 50 → 100 → 200 VUs) directly via Docker Compose:

```powershell
cd agent

# Execute for HTTP SSE (Unique cache mode):
docker compose --profile perftest run --rm -e STAGE_PROFILE=stepup -e CACHE_MODE=unique k6_perf_test

# Execute for gRPC Streaming (Unique cache mode):
docker compose --profile perftest run --rm -e STAGE_PROFILE=stepup -e CACHE_MODE=unique k6_grpc_perf_test
```

Detailed test scenario instructions, high-scale stress profiles (up to 1000 VUs), and report inspection procedures are documented in [`agent/docs/PERFORMANCE_TEST_GUIDE.md`](agent/docs/PERFORMANCE_TEST_GUIDE.md).

---

## 🧪 Running Automated Tests

### Agent Unit Tests
```bash
cd agent
pip install -r requirements.txt
pytest tests/unit/ -v
```

### gRPC Receipt Verification Test
```bash
cd agent
python test_grpc_receipt.py
```

### vLLM Serving Connectivity Check
```bash
cd agent/serving/vllm
python test_connection.py
```

### ASP.NET Core Website Tests
```bash
cd website
dotnet test
```

---

## 🔒 Security & Verifiable AI Receipts

The Travel Assistant System incorporates defense-in-depth principles:
* **Cryptographic AI Receipts:** Every completed stream signs an ECDSA (SECP256R1) token containing `session_id`, `timestamp`, and `SHA-256(response_text)`. Downstream services verify the digital signature using the agent's public key, guaranteeing that the advice was generated by the authorized model without tampering.
* **Input Validation:** gRPC server enforces hard prompt length limits (8000 characters) to mitigate buffer and denial-of-service vectors.
* **Credential Isolation:** Agent internal secrets (private keys, database URLs, MCP secrets) are isolated in the internal Docker network and never exposed to the public web interface.

---

## 🤝 Contributing

1. Fork the repository
2. Create a topic branch: `git checkout -b feature/your-feature-name`
3. Commit your changes following [Conventional Commits](https://www.conventionalcommits.org/): `git commit -m "feat: description"`
4. Push to branch: `git push origin feature/your-feature-name`
5. Open a Pull Request with verification test logs.

---

## 📄 License

---

<p align="center">
Built with LangGraph · ASP.NET Core · 9Router · vLLM · Qdrant · Prometheus
</p>
