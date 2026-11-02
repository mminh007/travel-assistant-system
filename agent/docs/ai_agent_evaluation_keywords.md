# 📚 AI Agent & LLM Evaluation: Research Keywords & Engineering Guide
## Cẩm Nang Tra Cứu Toàn Diện Về Kiểm Soát Chất Lượng, Đo Lường Hành Vi & A/B Testing Cho AI Agent

Tài liệu này tổng hợp toàn bộ các **thuật ngữ chuyên ngành (Keywords)**, khái niệm học thuật, công cụ mã nguồn mở và phương pháp luận tiêu chuẩn công nghiệp về **LLM Evaluation, AI Agent Quality Control, Online Behavioral Telemetry và A/B Testing**. 

---

## 📑 Mục Lục
1. [Bản Chất Mô Hình & Hiện Tượng Ảo Giác (Phenomenology & Model Biases)](#1-bản-chất-mô-hình--hiện-tượng-ảo-giác-phenomenology--model-biases)
2. [Khung Đánh Giá Tự Động & Chỉ Số Đo Lường (Automated Evaluation & Metrics)](#2-khung-đánh-giá-tự-động--chỉ-số-đo-lường-automated-evaluation--metrics)
3. [Đo Lường Trực Tuyến & Tín Hiệu Hành Vi Người Dùng (Online Telemetry & Behavioral Signals)](#3-đo-lường-trực-tuyến--tín-hiệu-hành-vi-người-dùng-online-telemetry--behavioral-signals)
4. [Thử Nghiệm A/B & Quản Trị Phát Hành (A/B Testing & Release Governance)](#4-thử-nghiệm-ab--quản-trị-phát-hành-ab-testing--release-governance)
5. [Bộ Dữ Liệu Chuẩn & Kiểm Thử Bảo Mật (Golden Benchmarks & Red Teaming)](#5-bộ-dữ-liệu-chuẩn--kiểm-thử-bảo-mật-golden-benchmarks--red-teaming)
6. [Công Cụ Mã Nguồn Mở & Nền Tảng Thực Chiến (Open-Source Tooling & Platforms)](#6-công-cụ-mã-nguồn-mở--nền-tảng-thực-chiến-open-source-tooling--platforms)
7. [Mẫu Truy Vấn Tìm Kiếm Nâng Cao (Arxiv, Google Scholar & GitHub)](#7-mẫu-truy-vấn-tìm-kiếm-nâng-cao-arxiv-google-scholar--github)

---

## 1. Bản Chất Mô Hình & Hiện Tượng Ảo Giác (Phenomenology & Model Biases)

Dùng để nghiên cứu lý do tại sao các mô hình sinh câu trả lời nghe rất thuyết phục nhưng thực chất bị sai hoặc vô nghĩa với nghiệp vụ.

| Thuật ngữ (Keyword) | Bản dịch / Ý nghĩa | Ý nghĩa chuyên sâu & Ứng dụng thực tế |
|---|---|---|
| **`Plausible Hallucination`** / **`Confident Hallucination`** | Ảo giác nghe có lý / Ảo giác tự tin | Hiện tượng LLM sinh ra thông tin sai lệch nhưng với giọng văn vô cùng tự tin, cấu trúc mạch lạc, khiến mắt thường khó phát hiện nếu không đối soát database. |
| **`Sycophancy in LLMs`** | Thiên kiến nịnh bợ / Đồng thuận mù quáng | Xu hướng LLM tự đồng ý với nhận định của người dùng hoặc tự đồng ý với output của chính nó trong các vòng suy luận lặp, che giấu lỗi sai logic. |
| **`LLM-as-a-Judge Limitations`** | Giới hạn của LLM làm giám khảo | Nghiên cứu về điểm mù của LLM khi tự chấm điểm (như position bias, verbosity bias - thích câu trả lời dài, self-enhancement bias - thiên vị mô hình cùng họ). |
| **`Intrinsic vs Extrinsic Hallucination`** | Ảo giác nội tại vs Ảo giác ngoại lai | *Intrinsic:* Câu trả lời mâu thuẫn trực tiếp với tài liệu ngữ cảnh (Context/RAG).<br>*Extrinsic:* Câu trả lời tự bịa thêm các chi tiết nằm ngoài dữ liệu được cung cấp. |
| **`Task-Oriented Dialogue Systems (TOD)`** | Hệ thống hội thoại hướng tác vụ | Phân nhánh AI hội thoại tập trung vào hoàn thành mục tiêu cụ thể (như đặt phòng khách sạn, book vé bay) thay vì trò chuyện phiếm (Open-domain Chitchat). |
| **`Language Drift in Multilingual LLMs`** | Trôi dạt ngôn ngữ trong mô hình đa ngữ | Hiện tượng mô hình mã nguồn mở (như Qwen) tự động chuyển sang tiếng Trung hoặc lẫn ký tự khi suy luận logic phức tạp trên prompt tiếng Việt/Anh. |

---

## 2. Khung Đánh Giá Tự Động & Chỉ Số Đo Lường (Automated Evaluation & Metrics)

Các chỉ số toán học và tiêu chuẩn thẩm định câu trả lời tự động bằng code hoặc mô hình tham chiếu.

| Thuật ngữ (Keyword) | Định nghĩa & Công thức cốt lõi | Cách ứng dụng trong hệ thống Travel Booking |
|---|---|---|
| **`Faithfulness` (Độ trung thực)** | $\frac{\text{Số luận điểm được chứng minh bởi Context}}{\text{Tổng số luận điểm Agent nêu ra}}$ | Đo lường xem các tiện ích khách sạn, giá phòng nêu ra có bắt nguồn 100% từ dữ liệu trả về của Tool/RAG hay không. |
| **`Answer Relevance` (Độ liên quan)** | Đo lường mức độ tương đồng ngữ nghĩa giữa câu trả lời và câu hỏi gốc. | Đảm bảo Agent không trả lời vòng vo kiểu bách khoa toàn thư khi khách chỉ hỏi giá phòng một đêm. |
| **`Context Precision & Recall`** | Độ chính xác và độ bao phủ của tài liệu RAG lấy về từ Vector Database. | Đánh giá thuật toán Hybrid Retrieval trên Qdrant có lấy trúng các khách sạn thỏa mãn bộ lọc của user hay không. |
| **`G-Eval` (Framework-agnostic LLM Judge)** | Phương pháp sử dụng LLM với Chain-of-Thought (CoT) và thang đo tiêu chí (Rubric) chi tiết. | Xây dựng tiêu chí chấm điểm chất lượng lịch trình du lịch (tính khả thi về thời gian di chuyển, sự hợp lý logic). |
| **`Deterministic Code Assertions`** | Kiểm thử tất định bằng mã nguồn (0% LLM). | Sử dụng Python/C# để kiểm tra: `check_in < check_out`, `hotel_price <= budget`, `hotel_id in database`. |
| **`Entity Grounding & Verification`** | Đối soát thực thể tự động. | Trích xuất tên khách sạn, số hiệu chuyến bay và kiểm tra chéo với bảng dữ liệu SQL Server / Amadeus API. |
| **`Constraint Satisfaction Rate (CSR)`** | Tỷ lệ tuân thủ các ràng buộc người dùng. | Kiểm tra xem Agent có bỏ sót bất kỳ yêu cầu nào của khách (như "phòng có ban công", "cho phép thú cưng") không. |

---

## 3. Đo Lường Trực Tuyến & Tín Hiệu Hành Vi Người Dùng (Online Telemetry & Behavioral Signals)

Đo lường mức độ hữu ích của AI Agent thông qua hành động thực tế của người dùng trên website thay vì khảo sát chủ quan.

| Thuật ngữ (Keyword) | Ý nghĩa nghiệp vụ | Phương pháp thu thập kỹ thuật |
|---|---|---|
| **`Implicit User Feedback`** | Phản hồi ngầm định qua hành vi | Thay vì bắt user bấm 1-5 sao, hệ thống theo dõi: sao chép văn bản (copy), click xem chi tiết khách sạn, click mở bản đồ. |
| **`Task Completion Rate (TCR)`** / **`Goal Conversion Rate`** | Tỷ lệ hoàn thành mục tiêu đặt phòng | Gắn `session_id` của Agent vào luồng tạo `BookingOrder` và thanh toán Stripe thành công. |
| **`Turn-to-Resolution (TTR)`** | Số bước tương tác để hoàn tất việc | Đếm số lượt tin nhắn từ lúc user hỏi đến khi bấm chọn phòng. TTR lý tưởng: 2 – 4 turns. TTR > 8 là dấu hiệu Agent vòng vo. |
| **`User Frustration Detection`** | Nhận diện khách hàng đang ức chế | Bộ lọc regex/embedding nhận diện các câu phàn nàn: *"Không đúng", "Tìm lại đi", "Tôi đã bảo là..."*. |
| **`Query Reformulation Rate`** | Tỷ lệ nhập lại câu hỏi | Khách hàng phải gõ lại cùng một ý định bằng từ khóa khác trong vòng 60 giây vì câu trả lời trước đó vô dụng. |
| **`Conversation Abandonment Rate`** | Tỷ lệ bỏ cuộc giữa chừng | Người dùng thoát khỏi website ngay sau câu trả lời của Agent mà không có bất kỳ tương tác tiếp theo nào. |
| **`Session Drop-off Knee-point`** | Điểm rơi rụng của phiên tương tác | Vị trí turn chat mà tại đó tỷ lệ người dùng thoát cao nhất (thường do độ trễ quá cao hoặc thông tin sai). |

---

## 4. Thử Nghiệm A/B & Quản Trị Phát Hành (A/B Testing & Release Governance)

Phương pháp luận so sánh giữa hai phiên bản Prompt, Mô hình (9Router vs vLLM) hoặc Graph Architecture.

| Thuật ngữ (Keyword) | Khái niệm & Kỹ thuật | Ứng dụng cụ thể cho Agent Engine |
|---|---|---|
| **`Prompt Regression Testing`** | Kiểm thử hồi quy Prompt | Chạy bộ kiểm thử tự động sau mỗi lần sửa `workflow.md` để đảm bảo không làm gãy các tính năng cũ đang chạy tốt. |
| **`Traffic Splitting for LLMs`** | Phân luồng lưu lượng truy cập | Dùng `Hash(SessionId) % 100` để chia 50% người dùng sang Variant A (Control) và 50% sang Variant B (Candidate). |
| **`Traffic Shadowing` / `Dark Launch`** | Nhân bản luồng request ngầm | Gửi bản sao câu hỏi thực tế của user tới Model/Prompt mới ngầm dưới background để đo latency/error mà không trả về UI. |
| **`CI/CD Quality Gates for LLMs`** | Cổng kiểm soát chất lượng tự động | Script trong GitHub Actions tự động `exit 1` và chặn merge PR nếu điểm Faithfulness < 0.90 hoặc CSR < 0.95. |
| **`LLMOps Telemetry Semantic Conventions`** | Quy chuẩn nhãn OpenTelemetry cho AI | Gắn nhãn chuẩn hóa: `gen_ai.system`, `gen_ai.request.model`, `gen_ai.response.completion_tokens`, `experiment.variant`. |
| **`Multi-Armed Bandit for Prompt Selection`** | Tối ưu hóa phân bổ prompt động | Tự động tăng tỷ lệ % traffic cho prompt có tỷ lệ Conversion cao hơn mà không cần chia 50/50 cứng. |

---

## 5. Bộ Dữ Liệu Chuẩn & Kiểm Thử Bảo Mật (Golden Benchmarks & Red Teaming)

Xây dựng bộ đề thi chuẩn hóa và các kịch bản kiểm thử biên/tấn công cho Agent.

| Thuật ngữ (Keyword) | Ý nghĩa kỹ thuật | Cách xây dựng cho hệ thống |
|---|---|---|
| **`Golden Dataset` / `Curated Ground Truth`** | Ngân hàng câu hỏi chuẩn có đáp án | Tập hợp 100–200 câu hỏi thực tế đại diện cho mọi use-case, có sẵn kỳ vọng về Tool cần gọi và ràng buộc dữ liệu. |
| **`Synthetic Test Data Generation`** | Tự sinh dữ liệu kiểm thử nhân tạo | Dùng mô hình mạnh (như GPT-4o) sinh ra hàng trăm biến thể câu hỏi phức tạp từ schema database khách sạn. |
| **`Red Teaming for AI Agents`** | Kiểm thử tấn công hộp đen/hộp trắng | Cố tình gửi các prompt lừa đảo (Prompt Injection, Jailbreak, yêu cầu giảm giá vé về 0 VNĐ, hỏi bí mật hệ thống). |
| **`AgentBench` / `ToolBench` / `WebArena`** | Bộ benchmark học thuật quốc tế | Các framework nghiên cứu chuẩn mực đo lường khả năng lập kế hoạch, tự sửa sai và gọi API của Autonomous Agents. |
| **`Edge-Case Stress Testing`** | Kiểm thử tải tình huống biên | Kiểm tra Agent khi dữ liệu tìm kiếm rỗng (Không còn chuyến bay), ngày bay trong quá khứ, ngân sách phi thực tế. |

---

## 6. Công Cụ Mã Nguồn Mở & Nền Tảng Thực Chiến (Open-Source Tooling & Platforms)

Các công cụ hàng đầu ngành đáng cài đặt và thử nghiệm:

```
┌────────────────────────────────────────────────────────────────────────┐
│                      HỆ SINH THÁI CÔNG CỤ ĐÁNH GIÁ                     │
├───────────────────┬───────────────────┬────────────────────────────────┤
│ Công cụ           │ Phân loại         │ Điểm mạnh nổi bật              │
├───────────────────┼───────────────────┼────────────────────────────────┤
│ 1. Ragas          │ RAG / Agent Eval  │ Đo Faithfulness & Relevance    │
│ 2. DeepEval       │ LLM Unit Testing  │ Tích hợp Pytest & CI/CD        │
│ 3. Promptfoo      │ CLI Test & A/B    │ Cực nhẹ, test Prompt Matrix    │
│ 4. Langfuse       │ Tracing & Evals   │ Gắn nhãn Score trực quan (Web) │
│ 5. Arize Phoenix  │ Observability     │ Tự động phân tích Evals        │
└───────────────────┴───────────────────┴────────────────────────────────┘
```

1. **[Ragas (ragas.io)](https://github.com/explodinggradients/ragas):**
   * *Mục đích:* Thư viện mã nguồn mở chuyên sâu nhất để đo lường RAG và Agent.
   * *Tích hợp:* Tính toán tự động điểm `faithfulness`, `answer_relevancy`, `context_recall`.
2. **[DeepEval (confident-ai)](https://github.com/confident-ai/deepeval):**
   * *Mục đích:* "Pytest dành cho LLMs". Cho phép viết assertion test:
     ```python
     assert_test(test_case, [faithfulness_metric, hallucination_metric])
     ```
3. **[Promptfoo (promptfoo.dev)](https://www.promptfoo.dev/):**
   * *Mục đích:* Công cụ dòng lệnh (CLI) nhẹ nhất để chạy ma trận test nhiều prompt khác nhau và xuất bảng so sánh HTML trực quan.
4. **[Langfuse (langfuse.com)](https://langfuse.com/):**
   * *Hiện diện:* Dự án của bạn **đã có sẵn container `langfuse_server`** trong `agent/docker-compose.tracing.yml`.
   * *Tính năng:* Tìm đọc tính năng **Scores & Evaluation SDK** để tự động chấm điểm trace và quản lý Dataset trực tiếp trên giao diện web.

---

## 7. Mẫu Truy Vấn Tìm Kiếm Nâng Cao (Arxiv, Google Scholar & GitHub)

Sử dụng trực tiếp các cú pháp tìm kiếm nâng cao dưới đây để tìm tài liệu nghiên cứu chuyên sâu:

### 1. Tìm kiếm Paper học thuật trên Arxiv / Google Scholar:
* `"LLM-as-a-judge" AND "self-enhancement bias" OR "sycophancy"`
* `"Evaluating Conversational AI" AND "Task-Oriented Dialogue" AND "Task Completion Rate"`
* `"Ragas: Automated Evaluation of Retrieval Augmented Generation"`
* `"G-Eval: NLG Evaluation using GPT-4 with Better Human Alignment"`
* `"Faithfulness metric" AND "Hallucination detection" AND "LLM"`

### 2. Tìm kiếm kiến trúc kỹ thuật thực chiến (Engineering Blogs):
* `site:netflixtechblog.com OR site:eng.uber.com "LLM evaluation" OR "A/B testing"`
* `site:booking.com "conversational AI" OR "recommender systems" evaluation`
* `"LLM evaluation in production" site:towardsdatascience.com OR site:medium.com`
* `"Continuous evaluation" LLM CI/CD pipeline`

### 3. Tìm kiếm GitHub Repositories mẫu:
* `topic:llm-evaluation stars:>500`
* `topic:rag-evaluation stars:>500`
* `filename:eval.py "ragas" OR "deepeval"`

---

## 📌 Khuyến Nghị Cho Dự Án Travel Booking

1. **Ưu tiên 1:** Đọc tài liệu của **Ragas** về 2 metrics `Faithfulness` và `Answer Relevance`.
2. **Ưu tiên 2:** Mở giao diện **Langfuse Web** đang chạy nội bộ tại `http://localhost:3000` và tìm hiểu mục **Datasets & Scores** để kích hoạt tính năng chấm điểm hội thoại online.
3. **Ưu tiên 3:** Bổ sung hàm code Python kiểm tra chéo giá phòng/chuyến bay trong database ngay tại `ChatStreamService` trước khi sinh AI Response Receipt.
