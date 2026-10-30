# 🚀 Hướng Dẫn Chạy Kiểm Thử Hiệu Năng & Khả Năng Chịu Tải
## Travel Assistant System — Multi-Agent & Hybrid RAG Stack

Tài liệu này cung cấp toàn bộ hướng dẫn, giải thích các kịch bản và **tổng hợp các câu lệnh chi tiết** để thực thi kiểm thử hiệu suất hệ thống từ Smoke test đến Step-up tải nặng 200 VUs trên cả hai giao thức: **HTTP SSE** và **gRPC Streaming**.

---

## 📌 Mục Lục
1. [Chuẩn Bị & Kiểm Tra Môi Trường](#1-chuẩn-bị--kiểm-tra-môi-trường)
2. [Cấu Trúc Bộ Kiểm Thử & 2 Giao Thức (HTTP vs gRPC)](#2-cấu-trúc-bộ-kiểm-thử--2-giao-thức-http-vs-grpc)
3. [Tổng Hợp Các Lệnh Chạy Test](#3-tổng-hợp-các-lệnh-chạy-test)
   - [Kịch bản 1: Step-up Load Test (10 → 50 → 100 → 200 VUs) — Mục tiêu chính](#kịch-bản-1-step-up-load-test-10--50--100--200-vus--mục-tiêu-chính)
   - [Kịch bản 2: Smoke Test (Kiểm tra nhanh 1-2 phút)](#kịch-bản-2-smoke-test-kiểm-tra-nhanh-1-2-phút)
   - [Kịch bản 3: Soak Test (Chạy bền 30 phút ở 50 VUs)](#kịch-bản-3-soak-test-chạy-bền-30-phút-ở-50-vus)
   - [Kịch bản 4: Spike Test (Bật tải đột ngột 200 VUs)](#kịch-bản-4-spike-test-bật-tải-đột-ngột-200-vus)
   - [Kịch bản 5: Test riêng từng mức độ câu hỏi (Low / Medium / High)](#kịch-bản-5-test-riêng-từng-mức-độ-câu-hỏi-low--medium--high)
4. [Theo Dõi Real-time Trên Dashboard](#4-theo-dõi-real-time-trên-dashboard)
5. [Xem & Quản Lý Báo Cáo Hiệu Năng (HTML & JSON Reports)](#5-xem--quản-lý-báo-cáo-hiệu-năng-html--json-reports)
6. [Xử Lý Sự Cố Thường Gặp (Troubleshooting)](#6-xử-lý-sự-cố-thường-gặp-troubleshooting)

---

## 1. Chuẩn Bị & Kiểm Tra Môi Trường

Mở **PowerShell** hoặc **Terminal** và di chuyển vào thư mục `agent`:

```powershell
cd d:\proj\Booking\agent
```

### Bước 1.1: Kiểm tra các container hạ tầng
Đảm bảo tất cả các container hệ thống đang chạy (`Up`):

```powershell
docker ps
```

Các container bắt buộc phải hoạt động:
* `booking_api_server` (FastAPI REST & SSE — port 8080)
* `booking_grpc_server` (gRPC Core Engine Streaming — port 50051)
* `booking_prometheus` (Prometheus Time-series DB — port 9090)
* `booking_grafana` (Grafana Dashboard — port 3001)
* `booking_redis` (Redis Cache & Checkpointer — port 6379)
* `booking_qdrant_server` (Qdrant Vector DB — port 6333)
* `booking_rabbitmq` (RabbitMQ Message Broker — port 5672)

### Bước 1.2: Bật hệ thống nếu chưa chạy
Nếu các container trên chưa bật, chạy lệnh sau để khởi động toàn bộ:

```powershell
docker compose up -d
```

---

## 2. Cấu Trúc Bộ Kiểm Thử & 2 Giao Thức (HTTP vs gRPC)

Bộ test nằm trọn vẹn trong thư mục `agent/load_tests/`:

* **`questions_db.json`**: Ngân hàng 60 câu hỏi du lịch thực tế, chia theo 3 mức độ:
  * **LOW (20 câu)**: Câu hỏi FAQ, tìm khách sạn đơn giản (đi qua route tắt `direct_executor`).
  * **MEDIUM (25 câu)**: Lập lịch trình 3-4 ngày, so sánh địa điểm (chạy qua `planner` + ReAct tool).
  * **HIGH (15 câu)**: Lập kế hoạch ngân sách chi tiết, tour dài ngày xuyên Việt (duyệt toàn bộ đồ thị LangGraph và cơ chế Critic/Rework).

* **Hai kịch bản kiểm thử song song:**

| Thuộc tính | Luồng HTTP SSE (`travel_perf_test.js`) | Luồng gRPC Stream (`travel_grpc_perf_test.js`) |
| :--- | :--- | :--- |
| **Kịch bản file** | `load_tests/travel_perf_test.js` | `load_tests/travel_grpc_perf_test.js` |
| **Docker Service** | `k6_perf_test` | `k6_grpc_perf_test` |
| **Giao thức** | HTTP/1.1 Server-Sent Events (SSE) | HTTP/2 gRPC Streaming |
| **Target URL** | `http://agent_api:8080/api/chat/stream` | `agent_grpc:50051` (`StreamChat`) |
| **Bảo mật** | Anonymous Token / User ID Header | ES256 AI Response Receipt Signature |
| **Báo cáo xuất ra** | `reports/http_test_{datetime}.html` & `.json` | `reports/grpc_test_{datetime}.html` & `.json` |

---

## 3. Tổng Hợp Các Lệnh Chạy Test

> **Lưu ý quan trọng**: Tất cả câu lệnh bên dưới đều chạy tại thư mục `d:\proj\Booking\agent`.

---

### Kịch bản 1: Step-up Load Test (10 → 50 → 100 → 200 VUs) — Mục tiêu chính

Kịch bản chuẩn leo bậc thang qua 4 mức tải trong ~17 phút:
* **00:00 – 03:00**: 10 VUs (Warm-up & xác lập Baseline)
* **03:00 – 07:00**: 50 VUs (Mức tải người dùng bình thường)
* **07:00 – 11:00**: 100 VUs (Tải cao — kiểm tra Continuous Batching của vLLM)
* **11:00 – 15:00**: 200 VUs (Mức tải cực đại — đo ngưỡng bão hòa và hàng đợi)
* **15:00 – 17:00**: Giảm dần về 0 VUs (Cool-down)

#### A. Chạy cho luồng HTTP SSE:
```powershell
# Chế độ Unique (Ép GPU/LLM xử lý 100% mọi request — Khuyên dùng đo Stress Test):
docker compose --profile perftest run --rm -e STAGE_PROFILE=stepup -e CACHE_MODE=unique k6_perf_test

# Chế độ Mixed (Mô phỏng 30% hit Semantic Cache trên Qdrant):
docker compose --profile perftest run --rm -e STAGE_PROFILE=stepup -e CACHE_MODE=mixed k6_perf_test
```

#### B. Chạy cho luồng gRPC Streaming:
```powershell
# Chế độ Unique qua gRPC:
docker compose --profile perftest run --rm -e STAGE_PROFILE=stepup -e CACHE_MODE=unique k6_grpc_perf_test

# Chế độ Mixed qua gRPC:
docker compose --profile perftest run --rm -e STAGE_PROFILE=stepup -e CACHE_MODE=mixed k6_grpc_perf_test
```

---

### Kịch bản Mở Rộng: High-Scale Stress Test (300 → 500 → 700 → 1000 VUs đồng thời)

Dùng để đánh giá ngưỡng bão hòa cực hạn (System Breaking Point) của hạ tầng vLLM Continuous Batching, Redis checkpointer và Agent backend.

#### 1. Chạy bậc thang tải cao liên tục (300 → 500 → 700 → 1000 VUs trong ~18 phút):
```powershell
# HTTP SSE:
docker compose --profile perftest run --rm -e STAGE_PROFILE=stepup_heavy k6_perf_test

# gRPC Streaming:
docker compose --profile perftest run --rm -e STAGE_PROFILE=stepup_heavy k6_grpc_perf_test
```

#### 2. Chạy cô lập từng mức tải đồng thời cụ thể:
* **Mức 300 users đồng thời (~6 phút):**
  ```powershell
  # HTTP SSE:
  docker compose --profile perftest run --rm -e STAGE_PROFILE=stress_300 k6_perf_test
  # gRPC:
  docker compose --profile perftest run --rm -e STAGE_PROFILE=stress_300 k6_grpc_perf_test
  ```

* **Mức 500 users đồng thời (~7 phút):**
  ```powershell
  # HTTP SSE:
  docker compose --profile perftest run --rm -e STAGE_PROFILE=stress_500 k6_perf_test
  # gRPC:
  docker compose --profile perftest run --rm -e STAGE_PROFILE=stress_500 k6_grpc_perf_test
  ```

* **Mức 700 users đồng thời (~8 phút):**
  ```powershell
  # HTTP SSE:
  docker compose --profile perftest run --rm -e STAGE_PROFILE=stress_700 k6_perf_test
  # gRPC:
  docker compose --profile perftest run --rm -e STAGE_PROFILE=stress_700 k6_grpc_perf_test
  ```

* **Mức 1000 users đồng thời (~9 phút):**
  ```powershell
  # HTTP SSE:
  docker compose --profile perftest run --rm -e STAGE_PROFILE=stress_1000 k6_perf_test
  # gRPC:
  docker compose --profile perftest run --rm -e STAGE_PROFILE=stress_1000 k6_grpc_perf_test
  ```
*(Lưu ý: Bạn cũng có thể dùng cú pháp alias ngắn gọn `-e STAGE_PROFILE=300`, `-e STAGE_PROFILE=500`, `-e STAGE_PROFILE=700`, `-e STAGE_PROFILE=1000`)*

---

### Kịch bản 2: Smoke Test (Kiểm tra nhanh 1-2 phút)

Dùng để xác nhận toàn bộ đường truyền và kết nối trước khi chạy bài test lớn (chạy 3 VUs trong 90 giây):

```powershell
# Test nhanh HTTP SSE:
docker compose --profile perftest run --rm -e STAGE_PROFILE=smoke k6_perf_test

# Test nhanh gRPC Streaming:
docker compose --profile perftest run --rm -e STAGE_PROFILE=smoke k6_grpc_perf_test
```

---

### Kịch bản 3: Soak Test (Chạy bền 30 phút ở 50 VUs)

Duy trì đều đặn 50 người dùng liên tục trong 30 phút. Mục đích phát hiện rò rỉ bộ nhớ (Memory Leak), tràn RAM Redis hoặc nghẽn hàng đợi RabbitMQ:

```powershell
# Soak Test HTTP:
docker compose --profile perftest run --rm -e STAGE_PROFILE=soak -e CACHE_MODE=mixed k6_perf_test

# Soak Test gRPC:
docker compose --profile perftest run --rm -e STAGE_PROFILE=soak -e CACHE_MODE=mixed k6_grpc_perf_test
```

---

### Kịch bản 4: Spike Test (Bật tải đột ngột 200 VUs)

Trong 10 giây đẩy vọt từ 0 lên 200 VUs, duy trì 3 phút rồi hạ tải:

```powershell
# Spike Test HTTP:
docker compose --profile perftest run --rm -e STAGE_PROFILE=spike -e CACHE_MODE=unique k6_perf_test

# Spike Test gRPC:
docker compose --profile perftest run --rm -e STAGE_PROFILE=spike -e CACHE_MODE=unique k6_grpc_perf_test
```

---

### Kịch bản 5: Test riêng từng mức độ câu hỏi (Low / Medium / High)

Đo đạc cô lập để xem từng loại câu hỏi tiêu tốn thời gian bao lâu:

#### Với HTTP SSE:
```powershell
# 1. Chỉ test câu hỏi DỄ (FAQ, tìm khách sạn):
docker compose --profile perftest run --rm -e COMPLEXITY_FILTER=low k6_perf_test

# 2. Chỉ test câu hỏi TRUNG BÌNH (Lập lịch trình 3-4 ngày):
docker compose --profile perftest run --rm -e COMPLEXITY_FILTER=medium k6_perf_test

# 3. Chỉ test câu hỏi PHỨC TẠP (Ngân sách chi tiết, tour dài ngày):
docker compose --profile perftest run --rm -e COMPLEXITY_FILTER=high k6_perf_test
```

#### Với gRPC Streaming:
```powershell
# 1. Chỉ test câu hỏi DỄ qua gRPC:
docker compose --profile perftest run --rm -e COMPLEXITY_FILTER=low k6_grpc_perf_test

# 2. Chỉ test câu hỏi TRUNG BÌNH qua gRPC:
docker compose --profile perftest run --rm -e COMPLEXITY_FILTER=medium k6_grpc_perf_test

# 3. Chỉ test câu hỏi PHỨC TẠP qua gRPC:
docker compose --profile perftest run --rm -e COMPLEXITY_FILTER=high k6_grpc_perf_test
```

---

## 4. Theo Dõi Real-time Trên Dashboard

Trong khi terminal đang chạy lệnh kiểm thử, mở trình duyệt để quan sát các chỉ số thời gian thực:

### 1. Grafana Dashboard
* **Địa chỉ:** [`http://localhost:3001`](http://localhost:3001)
* **Tài khoản mặc định:** `admin` / `admin`
* **Các dashboard cần mở:**
  * **`🔫 k6 Travel Performance Test Dashboard`** *(Khuyên dùng)*: Theo dõi bậc thang VU, Throughput (RPS), Latency P50/P95 theo 3 tầng câu hỏi, Hàng đợi vLLM và SSE/gRPC chunks/s.
  * **`Booking LangGraph Multi-Agent & Hybrid RAG Observability`**: Xem độ trễ từng Node trong LangGraph (`planner`, `travel_react_agent`, `evaluator`), số vòng lặp và tỉ lệ Semantic Cache.
  * **`vLLM Dashboard`**: Xem GPU KV Cache Usage %, số request đang pending, tốc độ sinh token (tok/s).

### 2. Prometheus
* **Địa chỉ:** [`http://localhost:9090`](http://localhost:9090)
* Truy vấn nhanh các metric chính:
  * `sse_active_streams` — Số lượng luồng kết nối SSE đồng thời.
  * `grpc_active_streams` — Số lượng luồng kết nối gRPC đồng thời.
  * `travel_e2e_ms_all` / `travel_grpc_e2e_ms_all` — Độ trễ tổng thể đo từ k6.
  * `travel_grpc_receipt_rate` — Tỷ lệ stream gRPC có biên lai ký số AI Receipt hợp lệ.
  * `vllm:num_requests_waiting` — Số lượng request bị ứ đọng chờ xử lý trên GPU.

---

## 5. Xem & Quản Lý Báo Cáo Hiệu Năng (HTML & JSON Reports)

Sau khi mỗi bài test hoàn thành, hệ thống sẽ **tự động lưu báo cáo vào thư mục riêng**:
📂 **`d:\proj\Booking\agent\load_tests\reports\`**

### Quy chuẩn đặt tên file tự động:
Mỗi lượt test sẽ sinh ra 1 cặp file `.html` (giao diện) và `.json` (dữ liệu thô) có gắn timestamp chính xác theo chuẩn `{protocol}_test_{datetime}`:

```text
agent/load_tests/reports/
├── http_test_20261030_111500.html     <-- Báo cáo chi tiết HTTP theo thời gian chạy
├── http_test_20261030_111500.json     <-- Dữ liệu JSON thô HTTP
├── grpc_test_20261030_113000.html     <-- Báo cáo chi tiết gRPC theo thời gian chạy
├── grpc_test_20261030_113000.json     <-- Dữ liệu JSON thô gRPC
├── latest_http_test.html              <-- Bản copy nhanh lần test HTTP gần nhất
├── latest_grpc_test.html              <-- Bản copy nhanh lần test gRPC gần nhất
└── latest_http_test.json / latest_grpc_test.json
```

*(Đồng thời hệ thống vẫn duy trì file `summary_report.html` và `summary_report.json` tại `agent/load_tests/` để đảm bảo tương thích ngược).*

### 1. Báo cáo giao diện trực quan HTML
* **Cách mở:** Nhấp đúp chuột vào file HTML tương ứng trong thư mục `reports/` để mở trên trình duyệt Chrome/Edge.
* **Nội dung bao gồm:**
  * **Thẻ KPI:** Tổng Requests / Streams, Throughput, Tỷ lệ lỗi (Error Rate %), Tỷ lệ trúng cache / Tỷ lệ ký số AI Receipt, Tổng chunks nhận được.
  * **Bảng phân tầng chi tiết độ trễ:** Thống kê P50, P90, P95 (SLA), Trung bình và TTFT P95 cho từng tier `Low`, `Medium`, `High`.
  * **Bảng kiểm tra SLA (Thresholds):** Đánh giá PASSED / FAILED theo tiêu chuẩn cam kết.

### 2. Dữ liệu thô JSON (Client-side metrics)
* File `latest_http_test.json` / `latest_grpc_test.json` chứa các chỉ số đo đạc từ **phía Client (k6 runner)**: min, max, p50, p90, p95, p99, count, error rate, chunk count.
* Dễ dàng import vào pandas / Python notebook hoặc Google Sheets để so sánh hiệu năng giữa HTTP và gRPC.

### 3. Xuất Báo Cáo Toàn Diện 360° (Gộp k6 + vLLM GPU + LangGraph System Metrics)
Nếu bạn cần một file JSON chứa **cả thông số Client-side (k6) lẫn toàn bộ thông số Server-side của vLLM và hệ thống** (GPU KV Cache %, Hàng đợi Waiting Queue, Tokens/sec, Độ trễ từng Node LangGraph, Safeguards) như trên Grafana Dashboard:

Chạy script sau tại thư mục `agent`:
```powershell
# Cho đợt test HTTP:
python load_tests/export_system_metrics.py --protocol http --minutes 20

# Cho đợt test gRPC:
python load_tests/export_system_metrics.py --protocol grpc --minutes 20
```
*Script sẽ tự động truy vấn Prometheus và tạo ra file `reports/latest_{protocol}_full_metrics.json` tổng hợp toàn diện cả 2 nguồn.*

---

## 6. Xử Lý Sự Cố Thường Gặp (Troubleshooting)

### Vấn đề 1: Xuất hiện `WARN Request Failed error="request timeout"` ở mức 100 – 200 VUs
* **Giải thích:** Đây **không phải lỗi code**, mà là kết quả xác định **điểm bão hòa (Knee-point)** của GPU. Khi 200 requests nặng đồng thời dồn vào, vLLM xếp hàng xử lý vượt quá thời gian timeout (120s – 300s) khiến k6 tự ngắt kết nối.
* **Kết luận cho báo cáo:** Ngưỡng phục vụ tối ưu của 1 GPU hiện tại là **10 – 50 concurrent users**, bắt đầu suy giảm từ **~80 – 100 users** và bão hòa ở **>120 users**.

### Vấn đề 2: Dừng khẩn cấp bài test đang chạy
Nếu muốn dừng ngay lập tức bài test đang chạy trong terminal:
* Bấm tổ hợp phím **`Ctrl + C`** trong cửa sổ terminal đang chạy k6.
* Hoặc mở cửa sổ terminal mới và chạy:
  ```powershell
  docker compose --profile perftest down
  ```

### Vấn đề 3: Kiểm tra log của Server khi có lỗi
* **Xem log HTTP API Server:**
  ```powershell
  docker logs booking_api_server --tail 50 -f
  ```
* **Xem log gRPC Core Server:**
  ```powershell
  docker logs booking_grpc_server --tail 50 -f
  ```
