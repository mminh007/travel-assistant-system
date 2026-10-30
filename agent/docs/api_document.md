# 🚀 Danh Sách Cổng & Link Truy Cập Dịch Vụ (Docker Compose)

Tài liệu tổng hợp các đường dẫn (URL), cổng kết nối (port), tài khoản mặc định và mô tả cho tất cả các service đang chạy qua Docker Compose trong dự án **Booking / Travel Assistant System**.

---

## 📌 Bảng Tổng Hợp Nhanh

| Dịch vụ | Container Name | Host Port / URL | Tài khoản mặc định | Mô tả |
| :--- | :--- | :--- | :--- | :--- |
| **FastAPI (Agent API)** | `booking_api_server` | [http://localhost:8080](http://localhost:8080)<br>Docs: [http://localhost:8080/docs](http://localhost:8080/docs) | *Không có* | REST API & SSE Streaming chính của Agent |
| **Qdrant** | `booking_qdrant_server` | [http://localhost:6333/dashboard](http://localhost:6333/dashboard)<br>API: `http://localhost:6333` | *Không có* | Vector Database & Dashboard quản lý Vector Collections |
| **Prometheus** | `booking_prometheus` | [http://localhost:9090](http://localhost:9090) | *Không có* | Time-series Database thu thập metrics hệ thống |
| **Grafana** | `booking_grafana` | [http://localhost:3001](http://localhost:3001) | `admin` / `admin` | Dashboard trực quan hóa metrics (vLLM & Agent) |
| **RabbitMQ Management** | `booking_rabbitmq` | [http://localhost:15672](http://localhost:15672)<br>AMQP: `localhost:5672` | `guest` / `guest` | Message Broker & Web UI quản lý hàng đợi tác vụ |
| **Redis** | `booking_redis` | `localhost:6379` | *Không có* | In-memory Cache & Quản lý Session |
| **Agent gRPC Engine** | `booking_grpc_server` | `localhost:50051`<br>Metrics: [http://localhost:8002](http://localhost:8002) | *Không có* | Engine streaming qua giao thức gRPC |

---

## 📖 Chi Tiết Từng Dịch Vụ

### 1. FastAPI Web Server (`agent_api`)
* **URL Trực tiếp**: [http://localhost:8080](http://localhost:8080)
* **Swagger UI (Interactive Docs)**: [http://localhost:8080/docs](http://localhost:8080/docs)
* **ReDoc**: [http://localhost:8080/redoc](http://localhost:8080/redoc)
* **Healthcheck**: [http://localhost:8080/healthz](http://localhost:8080/healthz) | [http://localhost:8080/readyz](http://localhost:8080/readyz)
* **Metrics Endpoint**: [http://localhost:8080/metrics](http://localhost:8080/metrics)
> ⚠️ **Lưu ý**: Cổng của FastAPI được cấu hình là **8080** (thay vì mặc định 8000) để tránh xung đột với các service khác.

### 2. Qdrant Vector Database (`qdrant_server`)
* **Web Dashboard**: [http://localhost:6333/dashboard](http://localhost:6333/dashboard)
* **REST API**: `http://localhost:6333`
* **gRPC Endpoint**: `localhost:6334`

### 3. Prometheus Monitoring (`prometheus`)
* **Web UI**: [http://localhost:9090](http://localhost:9090)
* **Targets Status**: [http://localhost:9090/targets](http://localhost:9090/targets) (kiểm tra trạng thái cào metrics của các container)
* **Rules / Alerts**: [http://localhost:9090/alerts](http://localhost:9090/alerts)

### 4. Grafana Dashboards (`grafana`)
* **Web UI**: [http://localhost:3001](http://localhost:3001)
* **Đăng nhập mặc định**:
  * **Username**: `admin`
  * **Password**: `admin`
> ℹ️ Cổng host được ánh xạ là **3001** (`3001:3000`). Hệ thống đã tự động cấu hình sẵn datasource Prometheus và các dashboard theo dõi vLLM / Agent.

### 5. RabbitMQ Broker (`rabbitmq_broker`)
* **Management Web UI**: [http://localhost:15672](http://localhost:15672)
* **Tài khoản mặc định**:
  * **Username**: `guest`
  * **Password**: `guest`
* **AMQP Connection URL**: `amqp://guest:guest@localhost:5672/`

### 6. Redis Server (`redis_cache`)
* **Port**: `6379`
* **Connection URL**: `redis://localhost:6379/0`

### 7. Agent gRPC Server (`agent_grpc`)
* **gRPC Server Port**: `50051`
* **Prometheus Metrics Port**: [http://localhost:8002/metrics](http://localhost:8002/metrics) *(map từ cổng 8001 trong container)*

---

## 🧩 Các Dịch Vụ Bổ Trợ Khác (Optional Profiles / Compose Files)

| Dịch vụ | File cấu hình | Host Port / URL | Tài khoản mặc định | Mô tả |
| :--- | :--- | :--- | :--- | :--- |
| **Langfuse Server** | `docker-compose.tracing.yml` | [http://localhost:3000](http://localhost:3000) | Tự đăng ký tài khoản đầu tiên | LLM Tracing & Observability |
| **Langfuse Postgres** | `docker-compose.tracing.yml` | `localhost:5432` | `langfuse` / `secretpassword` | Database lưu dữ liệu trace của Langfuse |
| **LangGraph Studio** | `docker-compose.studio.yml` | [http://localhost:8123](http://localhost:8123) | *Không có* | Giao diện đồ họa tương tác LangGraph |
| **9router** | `docker-compose.9router.yml` | [http://localhost:20128](http://localhost:20128) | *Không có* | Routing gateway |

---

## 🛠️ Lệnh Hữu Ích

* **Kiểm tra trạng thái container và port đang map**:
  ```bash
  docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
  ```

* **Xem log container (ví dụ FastAPI)**:
  ```bash
  docker logs -f booking_api_server
  ```

* **Đổi port FastAPI từ 8080 sang 8000 (nếu muốn)**:
  Trong file `agent/docker-compose.yml`, tìm đến service `agent_api` và sửa:
  ```yaml
  ports:
    - "8000:8080"
  ```
  Sau đó cập nhật lại container:
  ```bash
  cd agent
  docker compose up -d agent_api
  ```
