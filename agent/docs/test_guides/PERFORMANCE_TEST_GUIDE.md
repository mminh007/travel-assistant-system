# 🚀 Performance & Load Testing Execution Guide
## Travel Assistant System — Multi-Agent & Hybrid RAG Stack

This guide details execution procedures, test profiles, scenario descriptions, and **exact command lines** for benchmarking the system under load — ranging from quick smoke tests to high-concurrency step-up runs (up to 200–1000 Virtual Users) across two core streaming protocols: **HTTP SSE** and **gRPC Streaming**.

---

## 📌 Table of Contents
- [🚀 Performance \& Load Testing Execution Guide](#-performance--load-testing-execution-guide)
  - [Travel Assistant System — Multi-Agent \& Hybrid RAG Stack](#travel-assistant-system--multi-agent--hybrid-rag-stack)
  - [📌 Table of Contents](#-table-of-contents)
  - [1. Environment Verification \& Prerequisites](#1-environment-verification--prerequisites)
    - [Step 1.1: Verify infrastructure containers](#step-11-verify-infrastructure-containers)
    - [Step 1.2: Launch stack if not yet running](#step-12-launch-stack-if-not-yet-running)
  - [2. Test Suite Architecture \& Dual Protocols (HTTP vs gRPC)](#2-test-suite-architecture--dual-protocols-http-vs-grpc)
  - [3. Test Execution Commands](#3-test-execution-commands)
    - [Scenario 1: Step-Up Load Test (10 → 50 → 100 → 200 VUs) — Core Baseline](#scenario-1-step-up-load-test-10--50--100--200-vus--core-baseline)
      - [A. Execute for HTTP SSE:](#a-execute-for-http-sse)
      - [B. Execute for gRPC Streaming:](#b-execute-for-grpc-streaming)
    - [Scenario 2: High-Scale Stress Test (300 → 500 → 700 → 1000 VUs) — Breaking Point](#scenario-2-high-scale-stress-test-300--500--700--1000-vus--breaking-point)
      - [1. Continuous high-scale ramp (300 → 500 → 700 → 1000 VUs over ~18 minutes):](#1-continuous-high-scale-ramp-300--500--700--1000-vus-over-18-minutes)
      - [2. Isolated target VU tiers:](#2-isolated-target-vu-tiers)
    - [Scenario 3: Smoke Test (Fast 90s Verification)](#scenario-3-smoke-test-fast-90s-verification)
    - [Scenario 4: Soak Test (30-Minute Endurance at 50 VUs)](#scenario-4-soak-test-30-minute-endurance-at-50-vus)
    - [Scenario 5: Spike Test (Instantaneous Burst to 200 VUs)](#scenario-5-spike-test-instantaneous-burst-to-200-vus)
    - [Scenario 6: Complexity-Isolated Testing (Low / Medium / High)](#scenario-6-complexity-isolated-testing-low--medium--high)
      - [For HTTP SSE:](#for-http-sse)
      - [For gRPC Streaming:](#for-grpc-streaming)
  - [4. Real-Time Monitoring Dashboards](#4-real-time-monitoring-dashboards)
    - [1. Grafana Dashboards](#1-grafana-dashboards)
    - [2. Prometheus](#2-prometheus)
  - [5. Performance Report Management (HTML \& JSON Reports)](#5-performance-report-management-html--json-reports)
    - [File Naming Convention:](#file-naming-convention)
    - [1. Interactive HTML Reports](#1-interactive-html-reports)
    - [2. Full 360° Metrics Exporter (k6 Client + vLLM GPU + LangGraph System Metrics)](#2-full-360-metrics-exporter-k6-client--vllm-gpu--langgraph-system-metrics)
  - [6. Troubleshooting \& Known Bottlenecks](#6-troubleshooting--known-bottlenecks)
    - [Issue 1: `WARN Request Failed error="request timeout"` at 100–200 VUs](#issue-1-warn-request-failed-errorrequest-timeout-at-100200-vus)
    - [Issue 2: Aborting an Active Run](#issue-2-aborting-an-active-run)
    - [Issue 3: Reviewing Server Diagnostic Logs](#issue-3-reviewing-server-diagnostic-logs)

---

## 1. Environment Verification & Prerequisites

Open **PowerShell** or **Terminal** and navigate to the `agent` root directory:

```powershell
cd d:\proj\Booking\agent
```

### Step 1.1: Verify infrastructure containers
Ensure all supporting infrastructure containers are healthy and running (`Up`):

```powershell
docker ps
```

Mandatory operational containers:
* `booking_api_server` (FastAPI REST & SSE — port 8080)
* `booking_grpc_server` (gRPC Core Engine Streaming — port 50051)
* `booking_prometheus` (Prometheus Time-series DB — port 9090)
* `booking_grafana` (Grafana Dashboard — port 3001)
* `booking_redis` (Redis Cache & Checkpointer — port 6379)
* `booking_qdrant_server` (Qdrant Vector DB — port 6333)
* `booking_rabbitmq` (RabbitMQ Message Broker — port 5672)

### Step 1.2: Launch stack if not yet running
```powershell
docker compose up -d
```

---

## 2. Test Suite Architecture & Dual Protocols (HTTP vs gRPC)

All performance testing assets reside in `agent/load_tests/`:

* **`questions_db.json`**: Curated bank of 60 realistic travel queries divided across three complexity tiers:
  * **LOW (20 questions)**: FAQ queries, direct hotel lookups (routed via `direct_executor_init` bypass).
  * **MEDIUM (25 questions)**: 3-4 day itinerary planning, multi-attribute comparisons (routed via `planner` + ReAct tool loop).
  * **HIGH (15 questions)**: Detailed multi-day budgets, cross-city regional tours (exercising full LangGraph recursion, tools, critic evaluation, and rework).

* **Dual Test Runners:**

| Attribute                  | HTTP SSE (`travel_perf_test.js`)              | gRPC Streaming (`travel_grpc_perf_test.js`)          |
| :------------------------- | :-------------------------------------------- | :--------------------------------------------------- |
| **Script File**            | `load_tests/travel_perf_test.js`              | `load_tests/travel_grpc_perf_test.js`                |
| **Docker Compose Service** | `k6_perf_test`                                | `k6_grpc_perf_test`                                  |
| **Protocol**               | HTTP/1.1 Server-Sent Events (SSE)             | HTTP/2 gRPC Streaming (`StreamChat`)                 |
| **Target Address**         | `http://agent_api:8080/chat/stream`           | `agent_grpc:50051`                                   |
| **Security Validation**    | Anonymous Token / User ID Header              | Cryptographic ES256 AI Response Receipt verification |
| **Generated Output**       | `reports/http_test_{datetime}.html` & `.json` | `reports/grpc_test_{datetime}.html` & `.json`        |

---

## 3. Test Execution Commands

> **Important:** All commands must be run from the `d:\proj\Booking\agent` directory.

---

### Scenario 1: Step-Up Load Test (10 → 50 → 100 → 200 VUs) — Core Baseline

Standard 4-stage staircase load test (~17 minutes total):
* **00:00 – 03:00**: 10 VUs (Warm-up & baseline calibration)
* **03:00 – 07:00**: 50 VUs (Normal expected user load)
* **07:00 – 11:00**: 100 VUs (Heavy concurrency — stresses vLLM Continuous Batching)
* **11:00 – 15:00**: 200 VUs (Peak saturation — tests scheduling queue limits)
* **15:00 – 17:00**: Ramp down to 0 VUs (Cool-down)

#### A. Execute for HTTP SSE:
```powershell
# Unique Cache Mode (Forces 100% LLM/GPU execution — recommended for stress testing):
docker compose --profile perftest run --rm -e STAGE_PROFILE=stepup -e CACHE_MODE=unique k6_perf_test

# Mixed Cache Mode (Simulates real-world traffic with ~30% Semantic Cache hit rate):
docker compose --profile perftest run --rm -e STAGE_PROFILE=stepup -e CACHE_MODE=mixed k6_perf_test
```

#### B. Execute for gRPC Streaming:
```powershell
# Unique Mode via gRPC:
docker compose --profile perftest run --rm -e STAGE_PROFILE=stepup -e CACHE_MODE=unique k6_grpc_perf_test

# Mixed Mode via gRPC:
docker compose --profile perftest run --rm -e STAGE_PROFILE=stepup -e CACHE_MODE=mixed k6_grpc_perf_test
```

---

### Scenario 2: High-Scale Stress Test (300 → 500 → 700 → 1000 VUs) — Breaking Point

Designed to identify the physical saturation threshold (breaking point) of vLLM continuous batching, GPU VRAM, Redis checkpointing, and agent concurrency.

#### 1. Continuous high-scale ramp (300 → 500 → 700 → 1000 VUs over ~18 minutes):
```powershell
# HTTP SSE:
docker compose --profile perftest run --rm -e STAGE_PROFILE=stepup_heavy k6_perf_test

# gRPC Streaming:
docker compose --profile perftest run --rm -e STAGE_PROFILE=stepup_heavy k6_grpc_perf_test
```

#### 2. Isolated target VU tiers:
* **300 Concurrent Users (~6 minutes):**
  ```powershell
  docker compose --profile perftest run --rm -e STAGE_PROFILE=stress_300 k6_perf_test
  docker compose --profile perftest run --rm -e STAGE_PROFILE=stress_300 k6_grpc_perf_test
  ```

* **500 Concurrent Users (~7 minutes):**
  ```powershell
  docker compose --profile perftest run --rm -e STAGE_PROFILE=stress_500 k6_perf_test
  docker compose --profile perftest run --rm -e STAGE_PROFILE=stress_500 k6_grpc_perf_test
  ```

* **700 Concurrent Users (~8 minutes):**
  ```powershell
  docker compose --profile perftest run --rm -e STAGE_PROFILE=stress_700 k6_perf_test
  docker compose --profile perftest run --rm -e STAGE_PROFILE=stress_700 k6_grpc_perf_test
  ```

* **1000 Concurrent Users (~9 minutes):**
  ```powershell
  docker compose --profile perftest run --rm -e STAGE_PROFILE=stress_1000 k6_perf_test
  docker compose --profile perftest run --rm -e STAGE_PROFILE=stress_1000 k6_grpc_perf_test
  ```
*(Short aliases supported: `-e STAGE_PROFILE=300`, `-e STAGE_PROFILE=500`, `-e STAGE_PROFILE=700`, `-e STAGE_PROFILE=1000`)*

---

### Scenario 3: Smoke Test (Fast 90s Verification)

Quick pipeline sanity check running 3 VUs for 90 seconds prior to larger test runs:

```powershell
# HTTP SSE:
docker compose --profile perftest run --rm -e STAGE_PROFILE=smoke k6_perf_test

# gRPC Streaming:
docker compose --profile perftest run --rm -e STAGE_PROFILE=smoke k6_grpc_perf_test
```

---

### Scenario 4: Soak Test (30-Minute Endurance at 50 VUs)

Sustained load of 50 concurrent users over 30 minutes to detect memory leaks, Redis buffer bloat, or RabbitMQ queue starvation:

```powershell
# HTTP SSE:
docker compose --profile perftest run --rm -e STAGE_PROFILE=soak -e CACHE_MODE=mixed k6_perf_test

# gRPC Streaming:
docker compose --profile perftest run --rm -e STAGE_PROFILE=soak -e CACHE_MODE=mixed k6_grpc_perf_test
```

---

### Scenario 5: Spike Test (Instantaneous Burst to 200 VUs)

Rapidly surges from 0 to 200 VUs within 10 seconds, holds for 3 minutes, then cools down:

```powershell
# HTTP SSE:
docker compose --profile perftest run --rm -e STAGE_PROFILE=spike -e CACHE_MODE=unique k6_perf_test

# gRPC Streaming:
docker compose --profile perftest run --rm -e STAGE_PROFILE=spike -e CACHE_MODE=unique k6_grpc_perf_test
```

---

### Scenario 6: Complexity-Isolated Testing (Low / Medium / High)

Isolates execution to verify cost and latency characteristics by question difficulty:

#### For HTTP SSE:
```powershell
# Low Complexity Only (FAQs, simple hotel queries):
docker compose --profile perftest run --rm -e COMPLEXITY_FILTER=low k6_perf_test

# Medium Complexity Only (3-4 day itineraries):
docker compose --profile perftest run --rm -e COMPLEXITY_FILTER=medium k6_perf_test

# High Complexity Only (Multi-city budgets, complex tours):
docker compose --profile perftest run --rm -e COMPLEXITY_FILTER=high k6_perf_test
```

#### For gRPC Streaming:
```powershell
# Low Complexity:
docker compose --profile perftest run --rm -e COMPLEXITY_FILTER=low k6_grpc_perf_test

# Medium Complexity:
docker compose --profile perftest run --rm -e COMPLEXITY_FILTER=medium k6_grpc_perf_test

# High Complexity:
docker compose --profile perftest run --rm -e COMPLEXITY_FILTER=high -e CACHE_MODE=mixed k6_grpc_perf_test
```

---

## 4. Real-Time Monitoring Dashboards

While test commands execute, monitor live metrics via web browsers:

### 1. Grafana Dashboards
* **URL:** [`http://localhost:3001`](http://localhost:3001)
* **Default Credentials:** `admin` / `admin`
* **Key Dashboards:**
  * **`🔫 k6 Travel Performance Test Dashboard`**: Live VU ramp, Request Rate (RPS), P50/P95 latencies split across 3 complexity tiers, vLLM waiting queue depth, and streaming chunk throughput.
  * **`Booking LangGraph Multi-Agent & Hybrid RAG Observability`**: Individual node latency breakdowns (`planner`, `travel_react_agent`, `evaluator`), loop counts, and semantic cache hit rates.
  * **`vLLM Dashboard`**: GPU KV-cache usage %, active vs queued requests, and generation speed (tokens/s).

### 2. Prometheus
* **URL:** [`http://localhost:9090`](http://localhost:9090)
* **Key Queries:**
  * `sse_active_streams` — Active concurrent SSE streams.
  * `grpc_active_streams` — Active concurrent gRPC streams.
  * `travel_e2e_ms_all` / `travel_grpc_e2e_ms_all` — Client-perceived E2E duration from k6.
  * `travel_grpc_receipt_rate` — Fraction of responses containing valid cryptographic receipts.
  * `vllm:num_requests_waiting` — Requests queued waiting for GPU execution slots.

---

## 5. Performance Report Management (HTML & JSON Reports)

Upon test completion, standalone artifacts are automatically persisted to:
📂 **`d:\proj\Booking\agent\load_tests\reports\`**

### File Naming Convention:
Each run outputs a matching pair of visual `.html` and raw `.json` files stamped with `{protocol}_test_{datetime}`:

```text
agent/load_tests/reports/
├── http_test_20261030_111500.html     <-- Detailed HTML report for HTTP run
├── http_test_20261030_111500.json     <-- Raw client-side JSON metrics
├── grpc_test_20261030_113000.html     <-- Detailed HTML report for gRPC run
├── grpc_test_20261030_113000.json     <-- Raw client-side JSON metrics
├── latest_http_test.html              <-- Quick alias to most recent HTTP report
├── latest_grpc_test.html              <-- Quick alias to most recent gRPC report
└── latest_http_test.json / latest_grpc_test.json
```

### 1. Interactive HTML Reports
* Open directly in Chrome or Edge by double-clicking the target HTML file.
* Includes KPI summary tiles, per-complexity SLA threshold checks (Passed/Failed), and percentile latency tables (P50, P90, P95, TTFT).

### 2. Full 360° Metrics Exporter (k6 Client + vLLM GPU + LangGraph System Metrics)
To export a unified report combining client-side k6 numbers with server-side Prometheus metrics (GPU KV cache %, queue depth, node execution times, cost estimates):

```powershell
# For HTTP SSE run:
python load_tests/export_system_metrics.py --protocol http --minutes 20

# For gRPC run:
python load_tests/export_system_metrics.py --protocol grpc --minutes 20
```
This writes `reports/latest_{protocol}_full_metrics.json` merging both perspectives.

---

## 6. Troubleshooting & Known Bottlenecks

### Issue 1: `WARN Request Failed error="request timeout"` at 100–200 VUs
* **Root Cause:** Not a code bug, but the physical **knee-point (saturation point)** of single-GPU inference. When 200 heavy queries converge, vLLM continuous batching queues exceed client timeouts (120s–300s).
* **Capacity Benchmark:** A single RTX 3090 (24GB VRAM) running `Qwen2.5-3B-Instruct-AWQ` comfortably sustains **10–50 concurrent users**, shows scheduling queue growth at **~80–100 users**, and saturates at **>120 concurrent users**.

### Issue 2: Aborting an Active Run
* Press **`Ctrl + C`** in the active terminal running k6.
* Alternatively, run from another terminal:
  ```powershell
  docker compose --profile perftest down
  ```

### Issue 3: Reviewing Server Diagnostic Logs
* **FastAPI Server Logs:**
  ```powershell
  docker logs booking_api_server --tail 50 -f
  ```
* **gRPC Server Logs:**
  ```powershell
  docker logs booking_grpc_server --tail 50 -f
  ```
