# ✈️ Travel Assistant System

> A full-stack, AI-powered travel booking platform that pairs a production-grade **ASP.NET Core MVC** web application with a **multi-agent AI engine** built on LangGraph, OpenAI, and Anthropic Claude.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Getting Started](#getting-started)
  - [1. Clone the Repository](#1-clone-the-repository)
  - [2. Configure Environment Variables](#2-configure-environment-variables)
  - [3. Run the Agent Engine](#3-run-the-agent-engine)
  - [4. Run the Website](#4-run-the-website)
- [Agent Engine — Graph Architecture](#agent-engine--graph-architecture)
- [API Endpoints](#api-endpoints)
- [Infrastructure Services](#infrastructure-services)
- [Observability & Monitoring](#observability--monitoring)
- [Running Tests](#running-tests)
- [Contributing](#contributing)
- [License](#license)

---

## Overview

The **Travel Assistant System** is a comprehensive intelligent travel booking platform. It allows users to search for flights and hotels, create bookings, process payments, and interact with an AI travel advisor — all through a unified web interface.

The system is composed of two independently deployable components:

| Component | Technology | Purpose |
|---|---|---|
| **Website** | ASP.NET Core MVC (.NET 10) | User-facing portal for browsing, booking, and payments |
| **Agent Engine** | Python, LangGraph, FastAPI | Multi-agent AI backend for travel planning and intelligent Q&A |

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   Browser / Client                      │
└────────────────────────┬────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────┐
│            Website  (ASP.NET Core MVC / .NET 10)        │
│  ┌──────────────┐  ┌────────────┐  ┌────────────────┐  │
│  │ Controllers  │  │  Services  │  │   SignalR Hub  │  │
│  │ (MVC + API)  │  │ Amadeus /  │  │   (ChatHub)    │  │
│  │              │  │  Stripe /  │  │                │  │
│  │              │  │  Auth/JWT  │  │                │  │
│  └──────┬───────┘  └────────────┘  └────────┬───────┘  │
│         │  SQL Server (EF Core)              │ gRPC     │
└─────────┼─────────────────────────────────── ┼──────────┘
          │                                    │
┌─────────┼────────────────────────────────────┼──────────┐
│         │    Agent Engine  (Python / Docker)  │          │
│  ┌──────▼────────────┐           ┌────────────▼───────┐  │
│  │  FastAPI REST API │           │   gRPC Stream API  │  │
│  │    (port 8000)    │           │    (port 50051)    │  │
│  └──────────┬────────┘           └────────────────────┘  │
│             │                                            │
│  ┌──────────▼──────────────────────────────────────┐    │
│  │              LangGraph StateGraph                │    │
│  │  Phase 0: input_guardrail → intent routing      │    │
│  │  Phase 1: planner | direct_executor_init        │    │
│  │  Phase 2: travel_react_agent (ReAct loop)       │    │
│  │  Phase 3: finding_extractor → fact_checker      │    │
│  │  Phase 4: evaluator_agent (rework loop)         │    │
│  │  Phase 5: task_manager → final_synthesizer      │    │
│  └──────────┬──────────────────────────────────────┘    │
│             │                                            │
│  ┌──────────▼──────────────────────────────────────┐    │
│  │                Infrastructure                    │    │
│  │  Redis · Qdrant · RabbitMQ · Prometheus/Grafana │    │
│  └─────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────┘
```

---

## Tech Stack

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
| LLM Providers | OpenAI (GPT-4o, GPT-4o-mini) · Anthropic (Claude 3.5 Sonnet, Haiku) |
| Tool Protocol | MCP (Model Context Protocol) via `langchain-mcp-adapters` |
| Web Search | Tavily API |
| Vector Store | Qdrant (dense + BM25 hybrid retrieval) |
| Memory | Redis (session) + Qdrant (long-term) |
| Message Queue | RabbitMQ (async memory extraction worker) |
| Streaming API | gRPC (port 50051) |
| Observability | Prometheus · Grafana · Langfuse · Langsmith |
| Containerization | Docker + Docker Compose |

---

## Project Structure

```
travel-assistant-system/
├── website/                          # ASP.NET Core MVC application
│   ├── Controllers/                  # MVC controllers
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
    │   │   ├── config.py             # Graph configuration constants
    │   │   └── utils.py              # Shared graph utilities
    │   ├── api/                      # FastAPI routers & auth
    │   ├── core/                     # Settings, logger, metrics
    │   │   ├── settings.py           # Pydantic-based config (env-driven)
    │   │   ├── logger.py             # Structured logging
    │   │   └── metrics.py            # Prometheus metrics
    │   ├── mcp/                      # MCP tool definitions & client
    │   │   └── domains/              # Tool domains (web, core)
    │   ├── infrastructure/           # Qdrant & embedding providers
    │   ├── services/                 # Memory, LLM, streaming, user services
    │   ├── grpc_layer/               # gRPC server implementation
    │   ├── main.py                   # FastAPI app entry point
    │   └── worker_main.py            # RabbitMQ memory worker entry point
    ├── tests/unit/                   # Unit tests
    ├── load_tests/                   # k6 load test scripts
    ├── protos/                       # Shared gRPC .proto files
    ├── docs/                         # Additional documentation
    ├── docker-compose.yml            # Full stack deployment
    ├── docker-compose.tracing.yml    # Tracing/observability stack
    ├── dockerfile
    ├── langgraph.json                # LangGraph Studio config
    ├── prometheus.yml
    └── requirements.txt
```

---

## Prerequisites

### Website

- [.NET 10 SDK](https://dotnet.microsoft.com/download/dotnet/10.0)
- SQL Server (local or remote)
- Stripe account (for payment processing)
- Amadeus API credentials (for flight/hotel search)

### Agent Engine

- [Docker](https://www.docker.com/get-started) and [Docker Compose](https://docs.docker.com/compose/)
- OpenAI API key and/or Anthropic API key
- Tavily API key (web search)

---

## Getting Started

### 1. Clone the Repository

```bash
git clone https://github.com/mminh007/travel-assistant-system.git
cd travel-assistant-system
```

### 2. Configure Environment Variables

#### Agent Engine (`/agent/.env`)

Copy the example and fill in your secrets:

```bash
cp agent/.env.example agent/.env
```

Key variables to configure:

```env
# LLM Providers
OPENAI_API_KEY=sk-...
CLAUDE_API_KEY=sk-ant-...

# Web Search
TAVILY_API_KEY=tvly-...

# Infrastructure (auto-configured by Docker Compose)
REDIS_URL=redis://redis_cache:6379/0
RABBITMQ_URL=amqp://guest:guest@rabbitmq_broker:5672/
QDRANT_SERVER_HOST=qdrant_server
QDRANT_SERVER_PORT=6333

# Security — ECDSA keys for AI Response Receipts
SECURITY_AI_RECEIPT_PRIVATE_KEY=...
SECURITY_AI_RECEIPT_PUBLIC_KEY=...

# MCP JWT Secret
MCP_JWT_SECRET=...

# Observability (optional)
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

### 3. Run the Agent Engine

The agent engine is fully containerized. Create the shared Docker network first, then start all services:

```bash
cd agent

# Create the shared Docker network (one-time setup)
docker network create agent_network

# Build and start all services in detached mode
docker-compose up --build -d

# View logs
docker-compose logs -f
```

This starts the following containers:

| Container | Service | Port |
|---|---|---|
| `booking_api_server` | FastAPI REST API | `8000` |
| `booking_grpc_server` | gRPC Streaming Engine | `50051` |
| `booking_memory_worker` | Async Memory Extraction Worker | — |
| `booking_redis` | Redis (session + checkpointing) | `6379` |
| `booking_rabbitmq` | RabbitMQ (message queue) | `5672`, `15672` |
| `booking_qdrant_server` | Qdrant (vector database) | `6333`, `6334` |
| `booking_prometheus` | Prometheus (metrics) | `9090` |
| `booking_grafana` | Grafana (dashboards) | `3001` |

> **Note:** The `k6_load_test` service is optional and only runs when you set the `K6_SCRIPT` environment variable.

### 4. Run the Website

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

## Agent Engine — Graph Architecture

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
     │         └────────────────────────────────-┘
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

### LLM Tier Assignment

| Tier | Models | Nodes |
|---|---|---|
| **Tier 1** (Fast, low-cost) | `gpt-4o-mini` / `claude-3-haiku` | `input_guardrail`, `clarification_agent`, `finding_extractor` |
| **Tier 2** (Balanced) | `gpt-4o` / `claude-3-5-sonnet` | `planner`, `travel_react_agent`, `fact_checker`, `evaluator_agent`, `support_agent`, `final_synthesizer` |

### Programmatic Safeguards

| Safeguard | Constant | Action |
|---|---|---|
| Max ReAct iterations | `MAX_ITERATIONS = 8` | Force-route to `finding_extractor` |
| Max tool calls (budget) | `MAX_TOOL_CALLS = 10` | Force-route to `finding_extractor` |
| Duplicate tool detection | MD5 hash comparison | Block + force-route |
| Max rework cycles | `MAX_REWORK_CYCLES = 2` | Force-advance to `task_manager` |

---

## API Endpoints

### Agent REST API (FastAPI — port 8000)

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/chat` | Send a message; returns a streaming SSE response |
| `GET` | `/api/v1/health` | Health check |
| `GET` | `/metrics` | Prometheus metrics scrape endpoint |

### Agent gRPC API (port 50051)

Defined in `protos/chat.proto`. The `AgentService` exposes a `Chat` server-streaming RPC for real-time token delivery to the ASP.NET website.

---

## Infrastructure Services

| Service | URL | Default Credentials |
|---|---|---|
| FastAPI Docs (Swagger) | http://localhost:8000/docs | — |
| RabbitMQ Management | http://localhost:15672 | `guest` / `guest` |
| Qdrant Dashboard | http://localhost:6333/dashboard | — |
| Prometheus | http://localhost:9090 | — |
| Grafana | http://localhost:3001 | `admin` / `admin` |

> ⚠️ **Security:** Change all default credentials before deploying to a production environment.

---

## Observability & Monitoring

The agent engine ships with a complete observability stack:

- **Prometheus** — scrapes metrics exposed by `prometheus-client` at `/metrics`
- **Grafana** — pre-configured to pull from Prometheus; available at port `3001`
- **Langfuse / Langsmith** — optional LLM tracing (configure API keys in `.env`)
- **Structured Logging** — rotating log files written to `./logs/` (configurable via `LOGS_*` env vars)

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

## Running Tests

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

### Website

The website uses the standard .NET testing toolchain:

```bash
cd website
dotnet test
```

---

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature-name`
3. Commit your changes following [Conventional Commits](https://www.conventionalcommits.org/)
4. Push to your branch: `git push origin feature/your-feature-name`
5. Open a Pull Request

Please ensure all tests pass and new code is covered by unit tests before submitting a PR.

---

## License

This project is licensed under the [MIT License](LICENSE).

---

<p align="center">Built with ❤️ using LangGraph, ASP.NET Core, and modern AI tooling</p>
