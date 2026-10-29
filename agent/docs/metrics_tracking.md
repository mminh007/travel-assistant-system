# Tài Liệu Danh Sách & Mô Tả Các Thông Số Tracking (Prometheus & Grafana)

Hệ thống giám sát (Observability) của Travel Assistant Agent được thiết kế theo chuẩn **Prometheus Metrics**, tập trung theo dõi 8 nhóm chỉ số trọng yếu:
1. **Lưu lượng & Độ trễ Streaming (Traffic & E2E Latency)**
2. **Thực thi LangGraph Node & Suy luận LLM (Nodes & Execution)**
3. **Cơ chế Phòng vệ & Vòng lặp Agent (Safeguards & ReAct Loops)**
4. **Bộ nhớ đệm Ngữ nghĩa, Embedding & Hybrid RAG**
5. **Quản trị Token & Chi phí suy luận (Token Governance & Cost)**
6. **Định tuyến Độ phức tạp Động (Dynamic Complexity Routing)**
7. **Hiệu năng vLLM Serving Engine (GPU, KV Cache, Latency)**
8. **Chỉ số Đánh giá Tải từ k6 (Load Testing Metrics)**

---

## 1. Lưu lượng & Độ trễ Streaming (Traffic & E2E Latency)

Khai báo tại [`app/core/metrics.py#L13-L52`](../app/core/metrics.py).

| Tên Metric                          |   Loại    | Labels / Kích thước                                                                  | Mô tả & Ý nghĩa                                                                                                                                                                                                                                                        |
| :---------------------------------- | :-------: | :----------------------------------------------------------------------------------- | :--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `sse_active_streams`                |   Gauge   | *Không*                                                                              | **Số lượng luồng HTTP SSE đang kết nối đồng thời.** Giám sát lượng người dùng truy cập trực tiếp qua giao diện Web/SSE theo thời gian thực.                                                                                                                            |
| `sse_disconnect_total`              |  Counter  | `reason` (`completed`, `abrupt_client_disconnect`, `cache_hit`, `error`)             | **Tổng số phiên kết nối SSE bị đóng**, phân loại theo lý do kết thúc (hoàn thành đầy đủ, client tự ngắt sớm, trả về từ cache, hoặc lỗi gián đoạn). Giúp phát hiện tỷ lệ người dùng thoát ngang khi đang stream.                                                        |
| `grpc_active_streams`               |   Gauge   | *Không*                                                                              | **Số lượng luồng chat gRPC hai chiều (Bi-directional Stream) đang hoạt động.** Dùng giám sát tải giao tiếp giữa microservices hoặc client hiệu năng cao.                                                                                                               |
| `grpc_errors_total`                 |  Counter  | *Không*                                                                              | **Tổng số lỗi runtime xảy ra trên pipeline gRPC.** Đo lường độ ổn định của kênh truyền gRPC.                                                                                                                                                                           |
| `agent_requests_total`              |  Counter  | `source` (`http`, `grpc`), `status` (`completed`, `cache_hit`, `error`, `cancelled`) | **Tổng số request gửi đến Agent.** Dùng để tính Request Rate (req/s), Throughput và tỷ lệ thành công/thất bại theo từng giao thức.                                                                                                                                     |
| `agent_request_duration_seconds`    | Histogram | `source`, `status`<br>Buckets: `0.05s` → `60.0s`                                     | **Độ trễ toàn trình (End-to-End Latency) của một request.** Tính từ lúc nhận yêu cầu đến khi stream xong toàn bộ kết quả cho người dùng. Dùng theo dõi SLA p50, p95, p99.                                                                                              |
| `agent_time_to_first_token_seconds` | Histogram | `source`, `cache_status` (`hit`, `miss`)<br>Buckets: `0.02s` → `20.0s`               | **User-Perceived Time To First Token (TTFT).** Khoảng thời gian từ lúc gửi câu hỏi đến khi token đầu tiên hiển thị trên màn hình người dùng. Chỉ số quan trọng nhất phản ánh trải nghiệm tương tác (đặc biệt khi trúng Semantic Cache, TTFT giảm từ ~2s xuống < 50ms). |

---

## 2. Thực thi LangGraph Node & Suy luận LLM (Nodes & Execution)

Khai báo tại [`app/core/metrics.py#L57-L82`](../app/core/metrics.py).

| Tên Metric                         |   Loại    | Labels / Kích thước                                                                                                  | Mô tả & Ý nghĩa                                                                                                                                                                                        |
| :--------------------------------- | :-------: | :------------------------------------------------------------------------------------------------------------------- | :----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `agent_node_duration_seconds`      | Histogram | `node_name`<br>Buckets: `0.05s` → `20.0s`                                                                            | **Thời gian thực thi chi tiết của từng Node trong LangGraph** (ví dụ: `classifier`, `hotel_node`, `flight_node`, `synthesis_node`...). Giúp tìm điểm nghẽn (bottleneck finder) trong quy trình đồ thị. |
| `agent_llm_call_duration_seconds`  | Histogram | `node_name`, `tier` (`tier1`, `tier2`, `tier3`), `status` (`ok`, `truncated`, `error`)<br>Buckets: `0.05s` → `30.0s` | **Thời gian một lần gọi suy luận LLM**, đã bao gồm cả thời gian chờ semaphore kiểm soát tải concurrency. Đo đạc trực tiếp độ phản hồi của model ở từng node và từng tầng model.                        |
| `agent_llm_call_errors_total`      |  Counter  | `node_name`, `tier`, `error_type`                                                                                    | **Tổng số lần gọi LLM bị lỗi**, phân loại theo Node, Tier và loại lỗi (timeout, rate_limit, invalid_json, vLLM_error...).                                                                              |
| `agent_tool_call_duration_seconds` | Histogram | `tool_name`, `status`<br>Buckets: `0.01s` → `10.0s`                                                                  | **Độ trễ thực thi của các công cụ (Tools).** Đo thời gian chạy của các tool nội bộ (Local SQLite, Qdrant) và các tool ngoại vi (MCP Tools, Tavily Search, Booking API...).                             |

---

## 3. Cơ chế Phòng vệ & Vòng lặp Agent (Safeguards & ReAct Loops)

Khai báo tại [`app/core/metrics.py#L87-L104`](../app/core/metrics.py).

| Tên Metric                            |   Loại    | Labels / Kích thước                                                                               | Mô tả & Ý nghĩa                                                                                                                                                                                                    |
| :------------------------------------ | :-------: | :------------------------------------------------------------------------------------------------ | :----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `langgraph_iteration_count`           | Histogram | `domain`<br>Buckets: `1` → `15`                                                                   | **Phân phối số vòng lặp (ReAct cycles)** trong một phiên xử lý trước khi có câu trả lời cuối cùng. Giúp theo dõi hành vi tự suy luận của Agent.                                                                    |
| `langgraph_forced_termination_total`  |  Counter  | `domain`, `reason` (`max_iterations`, `budget_depleted`, `duplicate_action`, `max_rework_cycles`) | **Số lần kích hoạt cơ chế ngắt cưỡng bức (Hard Stop).** Đảm bảo Agent không bị rơi vào vòng lặp vô hạn, tiêu tốn quá nhiều chi phí hoặc lặp lại hành động sai.                                                     |
| `langgraph_duplicate_tool_call_total` |  Counter  | `tool_name`                                                                                       | **Số lần phát hiện và ngăn chặn hành động trùng lặp (Action Tracker).** Khi LLM cố gọi lại cùng một tool với cùng bộ tham số đầu vào trong một phiên làm việc, bộ lọc sẽ chặn lại để tiết kiệm token và thời gian. |

---

## 4. Bộ nhớ đệm Ngữ nghĩa, Embedding & Hybrid RAG

Khai báo tại [`app/core/metrics.py#L109-L141`](../app/core/metrics.py).

| Tên Metric                             |   Loại    | Labels / Kích thước                                                                               | Mô tả & Ý nghĩa                                                                                                                                            |
| :------------------------------------- | :-------: | :------------------------------------------------------------------------------------------------ | :--------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `semantic_cache_requests_total`        |  Counter  | `status` (`hit`, `miss`, `error`)                                                                 | **Tổng số lượt tra cứu Semantic Cache tại Qdrant.** Dùng để tính toán trực tiếp tỷ lệ Cache Hit Rate: $\frac{\text{hits}}{\text{total queries}}$.          |
| `semantic_cache_duration_seconds`      | Histogram | `operation` (`get`, `set`), `status` (`hit`, `miss`, `ok`, `error`)<br>Buckets: `0.005s` → `2.5s` | **Thời gian thực hiện đọc/ghi Semantic Cache**, bao gồm thời gian tạo embedding + tìm kiếm Vector ANN trên Qdrant + lọc Cosine Similarity.                 |
| `agent_embedding_duration_seconds`     | Histogram | `status` (`ok`, `error`)<br>Buckets: `0.005s` → `3.0s`                                            | **Độ trễ khi tạo Dense Vector Embeddings** từ embedding server (Qwen3-Embedding-4B hoặc 9Router).                                                          |
| `agent_rag_retrieval_duration_seconds` | Histogram | `collection`, `status` (`hit`, `empty`, `error`)<br>Buckets: `0.01s` → `3.0s`                     | **Độ trễ của thuật toán Hybrid Retrieval trên Qdrant**, kết hợp Vector ANN (Dense) + BM25 (Sparse) + Reciprocal Rank Fusion (RRF) để tái xếp hạng văn bản. |
| `agent_rag_retrieved_docs_count`       | Histogram | `collection`<br>Buckets: `0` → `10`                                                               | **Số lượng tài liệu/khách sạn tìm được và trả về** sau bước tìm kiếm và chấm điểm lọc ngưỡng.                                                              |

---

## 5. Quản trị Token & Chi phí suy luận (Token Governance & Cost)

Khai báo tại [`app/core/metrics.py#L146-L186`](../app/core/metrics.py).

| Tên Metric                          |   Loại    | Labels / Kích thước                                 | Mô tả & Ý nghĩa                                                                                                                                                 |
| :---------------------------------- | :-------: | :-------------------------------------------------- | :-------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `agent_token_usage_total`           |  Counter  | `tier` (`1`, `2`), `token_type` (`input`, `output`) | **Tổng lượng Token tiêu thụ lũy kế**, phân loại rõ ràng giữa Input Tokens (câu hỏi + context) và Output Tokens (câu trả lời sinh ra) theo từng cấp Model Tier.  |
| `agent_estimated_cost_usd`          | Histogram | Buckets: `$0.0001` → `$1.0`                         | **Ước tính chi phí quy đổi (USD)** cho mỗi lần triệu gọi LLM, tính theo bảng giá token tương ứng.                                                               |
| `agent_cost_per_tier_usd`           | Histogram | `tier`<br>Buckets: `$0.0001` → `$0.1`               | **Phân rã chi phí chi tiết theo từng Model Tier** (ví dụ: Tier 1 nhẹ tiết kiệm, Tier 2 thông minh hơn nhưng đắt hơn).                                           |
| `agent_node_input_tokens`           | Histogram | `node_name`, `tier`<br>Buckets: `100` → `4096`      | **Phân phối số lượng token đầu vào (Input Tokens) của từng Node.** Kiểm soát để không vượt trần Context Window (`max_context_tokens = 4096`).                   |
| `agent_node_output_tokens`          | Histogram | `node_name`, `tier`<br>Buckets: `32` → `2048`       | **Phân phối số token đầu ra (Output Tokens) của từng Node.** Dùng để tinh chỉnh và tối ưu thông số `NODE_MAX_TOKENS_*` cho từng tác vụ cụ thể.                  |
| `agent_node_output_truncated_total` |  Counter  | `node_name`, `tier`                                 | **Số lần câu trả lời bị cắt ngắn do chạm trần độ dài** (`finish_reason = length`). Cảnh báo cấu hình max output token đang bị quá hẹp so với nội dung cần sinh. |

---

## 6. Định tuyến Độ phức tạp Động (Dynamic Complexity Routing)

Khai báo tại [`app/core/metrics.py#L191-L221`](../app/core/metrics.py).

| Tên Metric                          |   Loại    | Labels / Kích thước                                             | Mô tả & Ý nghĩa                                                                                                                                            |
| :---------------------------------- | :-------: | :-------------------------------------------------------------- | :--------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `agent_request_complexity_total`    |  Counter  | `complexity` (`low`, `medium`, `high`), `intent_category`       | **Số lượng request phân loại theo mức độ phức tạp** tại Node Router. Cho biết tỷ lệ câu hỏi đơn giản (tra cứu nhanh) vs phức tạp (lên lịch trình đa điểm). |
| `agent_iterations_by_complexity`    | Histogram | `complexity`<br>Buckets: `1` → `12`                             | **Số vòng lặp thực tế mà Agent đã chạy** ứng với từng mức độ phức tạp của câu hỏi.                                                                         |
| `agent_tool_calls_by_complexity`    | Histogram | `complexity`<br>Buckets: `0` → `12`                             | **Số lần gọi công cụ thực tế** tương ứng với từng mức độ phức tạp.                                                                                         |
| `agent_rework_cycles_by_complexity` | Histogram | `complexity`<br>Buckets: `0` → `3`                              | **Số lần Agent phải sửa chữa lại câu trả lời (Rework / Quality Check)** do chưa thỏa mãn điều kiện đề ra, phân theo độ phức tạp.                           |
| `agent_soft_stop_trigger_total`     |  Counter  | `node_name`, `reason` (`low_iterations`, `low_tools`, `rework`) | **Số lần hệ thống chèn cảnh báo mềm (Soft-Stop Warning)** vào prompt yêu cầu LLM nhanh chóng tóm tắt và hoàn tất phản hồi thay vì tiếp tục gọi tool mới.   |

---

## 7. Hiệu năng vLLM Serving Engine (GPU, KV Cache, Latency)

Thu thập trực tiếp từ cổng `/metrics` của vLLM LLM Server (`Qwen/Qwen2.5-3B-Instruct-AWQ`) và Embedding Server (`Qwen/Qwen3-Embedding-4B`):

| Tên Metric                                                                               | Labels / Bộ lọc                          | Mô tả & Ý nghĩa                                                                                                                                            |
| :--------------------------------------------------------------------------------------- | :--------------------------------------- | :--------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `vllm:kv_cache_usage_perc` / `vllm:gpu_cache_usage_perc`                                 | `instance="vllm-llm"`                    | **Tỷ lệ % bộ nhớ KV Cache đang sử dụng trên GPU.** Cảnh báo nguy cơ tràn RAM GPU khi giá trị này tiến sát 100%.                                            |
| `vllm:prefix_cache_hits_total` / `vllm:prefix_cache_queries_total`                       | `instance="vllm-llm"`                    | **Số lượt trúng và tổng số lượt tra cứu Prompt Cache (Prefix Caching).** Phản ánh tỷ lệ tận dụng lại các đoạn prompt hệ thống dùng chung giữa các request. |
| `vllm:num_requests_running`                                                              | `instance="vllm-llm"` / `vllm-embedding` | **Số lượng request đang được GPU thực thi đồng thời.**                                                                                                     |
| `vllm:num_requests_waiting`                                                              | `instance="vllm-llm"`                    | **Số lượng request đang phải nằm chờ trong hàng đợi lập lịch (Queue Depth)** do máy chủ GPU quá tải.                                                       |
| `vllm:num_preemptions_total`                                                             | `instance="vllm-llm"`                    | **Số lần vLLM phải giải phóng (preempt) request đang chạy** do bộ nhớ GPU bị cạn kiệt giữa chừng.                                                          |
| `vllm:prompt_tokens_total`                                                               | `instance="vllm-llm"` / `vllm-embedding` | **Tổng số token đầu vào được nạp vào GPU (Prefill stage).** Đo lường Input Throughput (tokens/s).                                                          |
| `vllm:generation_tokens_total`                                                           | `instance="vllm-llm"`                    | **Tổng số token đầu ra được GPU sinh ra (Decode stage).** Đo lường Generation Throughput (tokens/s).                                                       |
| `vllm:time_to_first_token_seconds`                                                       | `instance="vllm-llm"`                    | **Thời gian tính toán token đầu tiên tại cấp độ vLLM Engine** (không bao gồm mạng nội bộ).                                                                 |
| `vllm:inter_token_latency_seconds` / `vllm:time_per_output_token_seconds`                | `instance="vllm-llm"`                    | **Thời gian sinh giữa 2 token liên tiếp (Inter-Token Latency / TPOT).** Chỉ số quyết định tốc độ chữ chạy (streaming fluidity) mượt mà cho người dùng.     |
| `vllm:e2e_request_latency_seconds`                                                       | `instance="vllm-llm"` / `vllm-embedding` | **Tổng thời gian xử lý toàn phần của một request bên trong engine vLLM.**                                                                                  |
| `vllm:request_queue_time_seconds`                                                        | `instance="vllm-llm"`                    | **Thời gian request phải nằm đợi trong hàng đợi trước khi bắt đầu xử lý.**                                                                                 |
| `vllm:request_success_total`                                                             | `finished_reason` (`stop`, `length`)     | **Số lượng request thành công**, phân theo lý do kết thúc (tự nhiên `stop` hay bị cắt `length`).                                                           |
| `vllm:spec_decode_num_accepted_tokens_total` / `vllm:spec_decode_num_draft_tokens_total` | `instance="vllm-llm"`                    | **Tỷ lệ chấp thuận token khi bật suy luận phỏng đoán (Speculative Decoding).**                                                                             |

---

## 8. Chỉ số Đánh giá Tải từ k6 (Load Testing Metrics)

Được cấu hình trong kịch bản test tải [`load_tests/http_stream_test.js`](../load_tests/http_stream_test.js) và [`load_tests/grpc_stream_test.js`](../load_tests/grpc_stream_test.js), đẩy vào Prometheus qua Remote Write:

| Tên Metric                 |  Loại   | Đơn vị | Mô tả & Ý nghĩa                                                                    |
| :------------------------- | :-----: | :----: | :--------------------------------------------------------------------------------- |
| `custom_e2e_duration_ms`   |  Trend  |   ms   | Thời gian trọn vòng đời một kết nối HTTP SSE từ client k6.                         |
| `custom_ttfb_ms`           |  Trend  |   ms   | Thời gian Time To First Byte (từ lúc gửi request HTTP đến khi nhận byte đầu tiên). |
| `custom_errors`            |  Rate   |   %    | Tỷ lệ % request HTTP bị lỗi hoặc ngắt kết nối bất thường trong quá trình test tải. |
| `custom_sse_chunks_total`  | Counter | chunks | Tổng số lượng data chunk SSE nhận về thành công từ máy chủ.                        |
| `custom_grpc_ttft_ms`      |  Trend  |   ms   | Thời gian từ lúc mở stream gRPC đến khi nhận tin nhắn đầu tiên từ Agent.           |
| `custom_grpc_e2e_ms`       |  Trend  |   ms   | Tổng thời gian thực hiện một phiên stream gRPC.                                    |
| `custom_grpc_errors`       |  Rate   |   %    | Tỷ lệ % luồng gRPC gặp lỗi trong quá trình test tải.                               |
| `custom_grpc_chunks_total` | Counter | chunks | Tổng số tin nhắn response gRPC nhận được.                                          |
