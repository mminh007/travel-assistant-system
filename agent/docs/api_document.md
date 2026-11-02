# 🚀 Service Ports & Access Directory (Docker Compose)

Comprehensive reference of URLs, exposed ports, default credentials, and descriptions for all services running via Docker Compose in the **Booking / Travel Assistant System**.

---

## 📌 Quick Summary Table

| Service | Container Name | Host Port / URL | Default Credentials | Description |
| :--- | :--- | :--- | :--- | :--- |
| **FastAPI (Agent REST API)** | `booking_api_server` | [http://localhost:8080](http://localhost:8080)<br>Docs: [http://localhost:8080/docs](http://localhost:8080/docs) | *None* | Primary REST API & SSE Streaming engine for Agent |
| **Qdrant Vector Database** | `booking_qdrant_server` | [http://localhost:6333/dashboard](http://localhost:6333/dashboard)<br>API: `http://localhost:6333` | *None* | Vector database and Web UI for vector collections |
| **Prometheus** | `booking_prometheus` | [http://localhost:9090](http://localhost:9090) | *None* | Time-series database scraping system and LLM metrics |
| **Grafana** | `booking_grafana` | [http://localhost:3001](http://localhost:3001) | `admin` / `admin` | Real-time monitoring dashboards (vLLM, Agent, k6 load test) |
| **RabbitMQ Management** | `booking_rabbitmq` | [http://localhost:15672](http://localhost:15672)<br>AMQP: `localhost:5672` | `guest` / `guest` | Message broker and web management interface for async memory pipeline |
| **Redis** | `booking_redis` | `localhost:6379` | *None* | In-memory cache, session store, and LangGraph checkpointer |
| **Agent gRPC Engine** | `booking_grpc_server` | `localhost:50051`<br>Metrics: [http://localhost:8002](http://localhost:8002) | *None* | High-performance bi-directional & server-streaming gRPC engine |

---

## 📖 Service Details

### 1. FastAPI Application Server (`agent_api`)
* **Base URL**: [http://localhost:8080](http://localhost:8080)
* **Swagger UI (Interactive Docs)**: [http://localhost:8080/docs](http://localhost:8080/docs)
* **ReDoc**: [http://localhost:8080/redoc](http://localhost:8080/redoc)
* **Healthchecks**: [http://localhost:8080/healthz](http://localhost:8080/healthz) | [http://localhost:8080/readyz](http://localhost:8080/readyz)
* **Metrics Endpoint**: [http://localhost:8080/metrics](http://localhost:8080/metrics)
> ⚠️ **Note:** FastAPI is configured on port **8080** (instead of standard 8000) to avoid collisions with local or remote vLLM LLM serving processes.

### 2. Qdrant Vector Database (`qdrant_server`)
* **Web Dashboard**: [http://localhost:6333/dashboard](http://localhost:6333/dashboard)
* **REST API**: `http://localhost:6333`
* **gRPC Endpoint**: `localhost:6334`

### 3. Prometheus Monitoring (`prometheus`)
* **Web UI**: [http://localhost:9090](http://localhost:9090)
* **Targets Status**: [http://localhost:9090/targets](http://localhost:9090/targets) (scraped container status)
* **Rules / Alerts**: [http://localhost:9090/alerts](http://localhost:9090/alerts)

### 4. Grafana Dashboards (`grafana`)
* **Web UI**: [http://localhost:3001](http://localhost:3001)
* **Default Credentials**:
  * **Username**: `admin`
  * **Password**: `admin`
> ℹ️ Host port mapped to **3001** (`3001:3000`). Pre-provisioned with Prometheus datasources and dashboards for vLLM, Agent runtime, and k6 performance testing.

### 5. RabbitMQ Broker (`rabbitmq_broker`)
* **Management Web UI**: [http://localhost:15672](http://localhost:15672)
* **Default Credentials**:
  * **Username**: `guest`
  * **Password**: `guest`
* **AMQP Connection URL**: `amqp://guest:guest@localhost:5672/`

### 6. Redis Server (`redis_cache`)
* **Port**: `6379`
* **Connection URL**: `redis://localhost:6379/0`

### 7. Agent gRPC Server (`agent_grpc`)
* **gRPC Server Port**: `50051`
* **Prometheus Metrics Port**: [http://localhost:8002/metrics](http://localhost:8002/metrics) *(mapped from port 8001 inside the container)*

---

## 🧩 Optional Profiles & Auxiliary Services

| Service | Configuration File | Host Port / URL | Default Credentials | Description |
| :--- | :--- | :--- | :--- | :--- |
| **Langfuse Server** | `docker-compose.tracing.yml` | [http://localhost:3000](http://localhost:3000) | Self-register first account | LLM tracing and observability UI |
| **Langfuse Postgres** | `docker-compose.tracing.yml` | `localhost:5432` | `langfuse` / `secretpassword` | Database storing trace telemetry |
| **LangGraph Studio** | `docker-compose.studio.yml` | [http://localhost:8123](http://localhost:8123) | *None* | Interactive graphical inspector for LangGraph workflows |
| **9Router** | `docker-compose.9router.yml` | [http://localhost:20128](http://localhost:20128) | *None* | Managed multi-provider AI proxy gateway |

---

## 🛠️ Useful Management Commands

* **Check container status and exposed port mappings**:
  ```bash
  docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
  ```

* **Inspect container logs (e.g., FastAPI)**:
  ```bash
  docker logs -f booking_api_server
  ```

* **Inspect gRPC streaming engine logs**:
  ```bash
  docker logs -f booking_grpc_server
  ```

* **Change FastAPI host port from 8080 to 8000 (if desired)**:
  In `agent/docker-compose.yml`, modify the `agent_api` service port mapping:
  ```yaml
  ports:
    - "8000:8080"
  ```
  Then recreate the container:
  ```bash
  cd agent
  docker compose up -d agent_api
  ```
