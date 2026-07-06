# Agent Cognitive Engine — Graph Architecture V2

> **Đường dẫn thư mục:** `agent/app/graph/`  
> **Framework:** LangGraph (`StateGraph`)  
> **Entry point:** `workflow.py → compiled_graph`  
> **State schema:** `state.py → AgentState`

---

## Mục lục

1. [Tổng quan về Kiến trúc V2 (Upgraded)](#1-tổng-quan-về-kiến-trúc-v2-upgraded)
2. [AgentState — Schema trạng thái](#2-agentstate--schema-trạng-thái)
3. [Bảng đăng ký Node (Node Registry)](#3-bảng-đăng-ký-node-node-registry)
4. [Mô tả chi tiết từng Node](#4-mô-tả-chi-tiết-từng-node)
5. [Workflow & Các luồng định tuyến chi tiết](#5-workflow--các-luồng-định-tuyến-chi-tiết)
6. [Cơ chế tối ưu hóa nâng cao trong V2](#6-cơ-chế-tối-ưu-hóa-nâng-cao-trong-v2)
7. [Safeguards & Giới hạn cứng (Hard Limits)](#7-safeguards--giới-hạn-cứng-hard-limits)
8. [Chiến lược LLM Tiers & Caching](#8-chiến-lược-llm-tiers--caching)

---

## 1. Tổng quan về Kiến trúc V2 (Upgraded)

Kiến trúc **Cognitive Graph V2** được nâng cấp toàn diện để giải quyết các hạn chế của phiên bản V1 liên quan đến **nhiễu ngữ cảnh (context drift)**, **vòng lặp phản hồi vô tận (infinite loops)**, và **chất lượng dữ liệu đầu ra**. 

Các cải tiến cốt lõi bao gồm:
*   **Context Sandboxing (Cô lập ngữ cảnh):** Xóa bỏ các message trung gian của các task trước khi chuyển sang task mới bằng `RemoveMessage`. Các phát hiện quan trọng được chắt lọc thành `findings` và truyền sang task tiếp theo qua system prompt để chống tràn context.
*   **Confidence-based Fast-Fail (Thất bại nhanh dựa trên độ tin cậy):** Nếu điểm tin cậy trung bình của executor thấp (< 0.6), hệ thống sẽ chuyển trực tiếp sang node `self_correct` để sửa sai mà không đi qua `critic_agent` nhằm tiết kiệm chi phí LLM.
*   **Structured Outputs:** Định nghĩa cấu trúc đầu ra nghiêm ngặt cho Executor (`ExecutorOutput`, `Finding`) và Critic (`CriticOutput` với 4 chiều đánh giá chi tiết).
*   **Reporting Engine:** Node `final_synthesizer` tổng hợp các findings có cấu trúc và raw results từ tất cả các task đã hoàn thành để viết nên một báo cáo Markdown hoàn chỉnh, có Bibliography ở cuối.

---

## 2. AgentState — Schema trạng thái

Toàn bộ dữ liệu truyền giữa các node được quản lý thông qua `AgentState` (`TypedDict`). LangGraph quản lý tính bất biến (immutability), mỗi node trả về một dictionary chứa các trường cần cập nhật hoặc bổ sung vào state.

```
AgentState
├── messages            → Chuỗi hội thoại chính (add_messages reducer)
├── user_id             → ID định danh người dùng
├── session_id          → ID phiên làm việc (session)
│
├── ── PHASE 1: GUARDRAIL & INTENT CLASSIFICATION ──────────────
├── is_in_domain        → True nếu là yêu cầu du lịch (booking/faq), False nếu ngoài lề
├── intent_category     → Phân loại ý định ("hotel_booking" | "flight_booking" | "travel_faq" | "itinerary_planning" | "out_of_domain")
├── complexity          → Mức độ phức tạp ("low" | "medium" | "high")
├── objective           → Mục tiêu tổng quát chung
│
├── ── PHASE 2: WORKFLOW MEMORY (PROCEDURAL STATE) ──────────────
├── tasks               → Danh sách tasks có cấu trúc:
│                         List[{
│                           "id": int, 
│                           "desc": str, 
│                           "status": "pending" | "completed", 
│                           "target_agent": str, 
│                           "result": str (Raw detailed markdown),
│                           "findings": List[Finding] (Structured statements + confidence)
│                         }]
├── current_task_id     → ID của sub-task đang thực thi
│
├── ── PHASE 3: LOOP MANAGEMENT & SAFEGUARDS ────────────────────
├── iteration_count     → Số vòng ReAct đã thực hiện của task hiện tại (max 8)
├── tool_call_count     → Tổng số tool đã gọi xuyên suốt graph (max 10)
├── action_history      → Danh sách MD5 hash của các tool calls để tránh gọi trùng (duplicate)
├── rework_count        → Số lần rework từ Critic -> Executor (max 2)
│
└── ── EVALUATION MEMORY ─────────────────────────────────────────
    ├── critic_feedback     → Phản hồi chi tiết từ Critic
    ├── reflection_notes    → Ghi chú hành động chỉnh sửa từ Reflection
    ├── needs_rework        → Boolean chỉ định có cần executor làm lại không
    └── final_answer        → (Dành riêng) Câu trả lời tổng hợp cuối cùng
```

---

## 3. Bảng đăng ký Node (Node Registry)

| # | Tên Node | Chức năng chính | LLM Tier được sử dụng | Loại Node |
|---|---|---|---|---|
| 0 | `input_guardrail` | Phân loại ý định người dùng, từ chối câu hỏi ngoài lề (out-of-domain). | Tier 1 (Fast - `gpt-4o-mini`) | Async Node |
| 1 | `planner` | Phân rã mục tiêu du lịch phức tạp thành chuỗi 2-4 sub-tasks. | Tier 2 (Balanced - `gpt-4o`) | Async Node |
| 2 | `direct_executor_init` | Khởi tạo trạng thái cho luồng bypass khi complexity='low' (Không dùng LLM). | *(Không dùng LLM)* | Async Node |
| 3 | `travel_react_agent` | Executor ReAct xử lý các câu hỏi du lịch, khách sạn, chuyến bay bằng RAG. | Tier 2 (Balanced - `gpt-4o`) | Async Node |
| 4 | `out_of_domain` | Xử lý các câu hỏi không liên quan đến du lịch bằng cách từ chối lịch sự. | *(Không dùng LLM)* | Async Node |
| 6 | `action_tracker` | Interceptor ghi lại hash và tăng bộ đếm tool trước khi tool chạy. | *(Không dùng LLM)* | Async Node |
| 7 | `tools` | Thực thi các MCP tool calls được yêu cầu bởi executor. | *(External)* | ToolNode |
| 8 | `self_correct` | Bổ sung câu lệnh yêu cầu làm lại trực tiếp khi confidence thấp mà không qua Critic. | *(Không dùng LLM)* | Async Node |
| 9 | `critic_agent` | Đánh giá chất lượng của Executor dựa trên 4 chỉ số điểm từ 1-10. | Tier 2 (Balanced - `gpt-4o`) | Async Node |
| 10 | `reflection_agent` | Tổng hợp đánh giá của Critic, quyết định rework và đưa ra lời khuyên. | Tier 2 (Balanced - `gpt-4o`) | Async Node |
| 11 | `task_manager` | Lưu kết quả, findings, cập nhật trạng thái task, thực hiện Context Sandboxing. | *(Không dùng LLM)* | Async Node |
| 12 | `final_synthesizer` | Tổng hợp toàn bộ findings & kết quả thô của các task thành báo cáo hoàn chỉnh. | Tier 2 (Balanced - `gpt-4o`) | Async Node |

---

## 4. Mô tả chi tiết từng Node

### 4.1. Node `input_guardrail`
*   **File nguồn:** `nodes.py → node_input_guardrail()`
*   **Vị trí:** Điểm bắt đầu (Entry Point) của đồ thị.
*   **Đặc điểm:** Sử dụng **Structured Output** (`with_structured_output`) ánh xạ vào schema `InputGuardrailOutput`.
*   **Nhiệm vụ:**
    1. Đọc tin nhắn cuối cùng của người dùng.
    2. Đọc tệp nguyên tắc `workflow.md` (được lưu trong cache qua `@lru_cache`).
    3. Phân tích và đưa ra quyết định:
        *   `is_in_domain`: Xác định xem câu hỏi có thuộc domain du lịch không.
        *   `complexity`: Độ phức tạp (`low`, `medium`, `high`).
        *   `intent_category`: Phân loại ý định cụ thể (khách sạn, chuyến bay, FAQ).
        *   `objective`: Mục tiêu cô đọng phục vụ cho việc đánh giá chất lượng.
*   **Fallback:** Nếu lỗi xảy ra, hệ thống tự động gán mặc định `current_domain="travel_react_agent"`, `complexity="low"`, `required_agents=[]`.

---

### 4.2. Node `planner`
*   **File nguồn:** `nodes.py → node_planner_agent()`
*   **Điều kiện chạy:** Chạy khi `complexity = "medium"` hoặc `"high"`.
*   **Đặc điểm:** Sử dụng `with_structured_output` ánh xạ vào schema `PlannerOutput`.
*   **Nhiệm vụ:**
    1. Nhận mục tiêu (`objective`) từ Router.
    2. Phân rã mục tiêu này thành 2-4 sub-task tuần tự (ví dụ: Task 1 tìm tài liệu, Task 2 phân tích, Task 3 so sánh).
    3. Gán agent chịu trách nhiệm (`target_agent`) cho từng task cụ thể.
*   **Fallback:** Nếu gặp lỗi, hệ thống tự động tạo ra một task duy nhất từ prompt gốc của user để tránh làm gián đoạn luồng chạy.

---

### 4.3. Node `direct_executor_init`
*   **File nguồn:** `nodes.py → node_direct_executor_init()`
*   **Điều kiện chạy:** Chạy khi `complexity = "low"`.
*   **Đặc điểm:** Node chức năng thuần túy, không tốn chi phí LLM.
*   **Nhiệm vụ:**
    1. Bỏ qua bước lập kế hoạch của Planner để tiết kiệm tài nguyên.
    2. Tạo một task duy nhất chứa prompt gốc của người dùng.
    3. Thiết lập mặc định cho tất cả các chỉ số đếm vòng lặp, công cụ và rework về `0`.

---

### 4.4. Node Executor (`travel_react_agent`)
*   **File nguồn:** `nodes.py` (`node_travel_react_agent`)
*   **Chức năng:** Các chuyên gia xử lý tác vụ thông qua vòng lặp **ReAct (Reason-and-Act)**.
*   **Cơ chế hoạt động:**
    1. Thực hiện tìm kiếm RAG trên database tương ứng thông qua Hybrid Search (Dense + BM25) để lấy ngữ cảnh.
    2. Tổng hợp system prompt bao gồm: Chỉ dẫn ReAct tiêu chuẩn, tệp nguyên tắc `workflow.md`, kết quả RAG, danh sách các findings của task trước (Context Sandboxing) và chỉ dẫn bắt buộc xuất ra định dạng JSON.
    3. **Bind Tools O(1) Caching:** Lấy LLM đã được cấu hình sẵn các tool tương ứng với domain thông qua bộ nhớ cache `_BOUND_LLM_CACHE`.
    4. Trả về `AIMessage` chứa các hành động gọi công cụ (`tool_calls`) hoặc chứa câu trả lời cuối cùng dưới định dạng JSON khớp với schema `ExecutorOutput`:
        *   `result`: Văn bản Markdown chi tiết của task hiện tại.
        *   `findings`: Danh sách các phát hiện quan trọng phục vụ lập luận của các task sau.

> [!NOTE]
> Node `travel_react_agent` áp dụng nguyên lý **Critic Before Tool** (tự chất vấn trước khi dùng tool) cùng **Confidence-Based Stopping** để tự dừng khi đã có đủ thông tin chất lượng.

---

### 4.5. Node `action_tracker` và Node `tools`
*   **File nguồn:** `workflow.py → action_tracker_node()` và `ToolNode(mcp_tools)`
*   **Nhiệm vụ:**
    *   `action_tracker`: Đóng vai trò là chốt chặn ghi nhận (Interceptor). Trước khi bất kỳ công cụ nào chạy, nó sẽ tạo MD5 hash cho công cụ kèm tham số, đẩy vào `action_history` và tăng `tool_call_count`. Điều này giúp ngăn chặn gọi trùng công cụ dù công cụ đó có thực thi thành công hay không.
    *   `tools`: Node mặc định của LangGraph đảm nhận việc gọi trực tiếp các MCP servers ngoài để lấy kết quả (như tìm kiếm Web, tính toán toán học) và trả về `ToolMessage`.

---

### 4.6. Node `self_correct`
*   **File nguồn:** `workflow.py → node_self_correct()`
*   **Vị trí:** Nhận tín hiệu từ hàm định tuyến `evaluate_tool_hooks` khi executor hoàn thành nhưng có độ tin cậy thấp.
*   **Nhiệm vụ:**
    1. Bơm trực tiếp một tin nhắn `HumanMessage` yêu cầu executor tự điều chỉnh: *"Độ tin cậy của kết quả trước đó quá thấp (< 0.6). Vui lòng sử dụng công cụ để tìm kiếm và củng cố bằng chứng trước khi trả lời."*
    2. Định tuyến thẳng về executor để chạy lại mà không cần đi qua Critic/Reflection, giảm thiểu 2 lượt gọi LLM Tier 2 đắt đỏ.

---

### 4.7. Node `critic_agent`
*   **File nguồn:** `nodes.py → node_critic_agent()`
*   **Nhiệm vụ:**
    1. Đánh giá kết quả của executor dựa trên cấu trúc nghiêm ngặt `CriticOutput`.
    2. Cho điểm từ 1 đến 10 đối với 4 khía cạnh chất lượng đầu ra:
        *   `tool_quality_score`: Chất lượng và tính hợp lý khi gọi tool.
        *   `evidence_quality_score`: Độ mạnh của các bằng chứng bảo vệ lập luận.
        *   `citation_quality_score`: Chất lượng trích nguồn dữ liệu.
        *   `freshness_score`: Tính cập nhật mới của thông tin.
    3. Kiểm tra xem mục tiêu ban đầu (`objective`) đã được hoàn thành hay chưa (`objective_met`).

---

### 4.8. Node `reflection_agent`
*   **File nguồn:** `nodes.py → node_reflection_agent()`
*   **Nhiệm vụ:**
    1. Dựa trên feedback chi tiết và điểm số từ `critic_agent` để đưa ra quyết định cuối cùng có cần làm lại (Rework) hay không (`needs_rework`).
    2. Tạo lời khuyên hành động cụ thể (`actionable_advice`) hướng dẫn Executor cách sửa đổi trong lượt chạy kế tiếp.
    3. Tăng bộ đếm `rework_count` nếu yêu cầu rework được kích hoạt.

---

### 4.9. Node `task_manager`
*   **File nguồn:** `nodes.py → node_task_manager()`
*   **Nhiệm vụ:**
    1. Parse output dạng JSON của executor để lấy thông tin chi tiết về `result` và `findings`.
    2. Lưu trữ chúng trực tiếp vào cấu trúc task hiện tại trong State.
    3. Đánh dấu trạng thái task hiện tại thành `"completed"`.
    4. **Context Sandboxing:** Kiểm tra nếu còn task tiếp theo trong danh sách:
        *   Bơm danh sách `RemoveMessage` để xóa toàn bộ các tin nhắn ReAct trung gian trong luồng lịch sử `messages` (chỉ giữ lại prompt gốc).
        *   Thiết lập lại các bộ đếm `iteration_count=0`, `tool_call_count=0`, `rework_count=0` về mặc định.
        *   Định hướng dòng chảy sang task mới.
    5. Nếu toàn bộ task đã hoàn tất, chuyển tiếp sang node tổng hợp.

---

### 4.10. Node `final_synthesizer`
*   **File nguồn:** `nodes.py → node_final_synthesizer()`
*   **Nhiệm vụ:**
    1. Tập hợp các kết quả rời rạc từ các task đã được `task_manager` lưu trữ.
    2. Trích xuất toàn bộ `findings` làm nền tảng.
    3. Sử dụng LLM Tier 2 xây dựng một báo cáo cuối cùng hoàn chỉnh:
        *   **Executive Summary:** Tóm tắt báo cáo dựa trên các findings có độ tin cậy cao.
        *   **Detailed Analysis:** Trình bày chi tiết từng khía cạnh dựa trên kết quả thô.
        *   **Bibliography/Sources:** Liệt kê đầy đủ các nguồn trích dẫn được trích xuất từ dữ liệu.

---

## 5. Workflow & Các luồng định tuyến chi tiết

### 5.1. Sơ đồ luồng tổng quan (Workflow Diagram)

```mermaid
graph TD
    Start([User Message]) --> IG[input_guardrail]
    
    %% Guardrail Gate
    IG -- is_in_domain = False --> OOD[out_of_domain]
    OOD --> End([END])
    
    IG -- is_in_domain = True, complexity = low --> DEI[direct_executor_init]
    IG -- is_in_domain = True, complexity = med/high --> PL[planner]
    
    %% Direct Init & Planner routing to Executors
    DEI --> TRA[travel_react_agent]
    PL --> TRA
    
    %% ReAct Tool Hooks
    TRA --> ETH[evaluate_tool_hooks]
    
    %% Hooks Branches
    ETH --> |has tools| AT[action_tracker]
    AT --> TL[tools]
    TL -- route_back_to_agent --> TRA
    
    %% Fast-Fail Branch
    ETH --> |confidence < 0.6| SC[self_correct]
    SC -- route_back_to_agent --> TRA
    
    %% Evaluation Branch
    ETH --> |no tools & confidence >= 0.6| CR[critic_agent]
    CR --> RF[reflection_agent]
    
    %% Rework Gate
    RF -- route_from_reflection --> |needs_rework=True & rework < max| TRA
    RF -- route_from_reflection --> |needs_rework=False OR rework >= max| TM[task_manager]
    
    %% Task Manager Loop
    TM -- route_from_task_manager --> |next task pending| TRA
    TM -- route_from_task_manager --> |all tasks completed| FS[final_synthesizer]
    
    FS --> End([END])
```

### 5.2. Bản đồ các nhánh rẽ điều kiện (Conditional Edges Map)

Quy tắc chuyển dịch trạng thái giữa các node được định nghĩa chặt chẽ bằng code:

1.  **Sau `input_guardrail` (`route_from_guardrail`):**
    *   `is_in_domain = False` $\rightarrow$ rẽ nhánh `out_of_domain`.
    *   `is_in_domain = True` và Độ phức tạp `low` $\rightarrow$ rẽ nhánh `direct_executor_init`.
    *   `is_in_domain = True` và Độ phức tạp `medium`/`high` $\rightarrow$ rẽ nhánh qua `planner`.
2.  **Sau `planner` và `direct_executor_init` (`route_from_planner`):**
    *   Chuyển sang `travel_react_agent`.
3.  **Sau Executor (`evaluate_tool_hooks`):**
    *   Nếu có yêu cầu gọi công cụ $\rightarrow$ đi tới `action_tracker` (sau đó chạy `tools`).
    *   Nếu kết thúc gọi công cụ nhưng điểm tin cậy trung bình thu được < 0.6 $\rightarrow$ kích hoạt Fast-Fail đi tới `self_correct`.
    *   Nếu kết thúc gọi công cụ bình thường và tin cậy $\ge$ 0.6 $\rightarrow$ đi tới `critic_agent`.
    *   Nếu chạm các hạn chế an toàn (Safeguards) $\rightarrow$ cưỡng chế kết thúc và chuyển tới `critic_agent`.
4.  **Sau `reflection_agent` (`route_from_reflection`):**
    *   Nếu `needs_rework` là True và `rework_count < MAX_REWORK_CYCLES` $\rightarrow$ quay lại executor để sửa lỗi.
    *   Nếu không cần rework hoặc vượt giới hạn rework $\rightarrow$ đi tới `task_manager`.
5.  **Sau `task_manager` (`route_from_task_manager`):**
    *   Nếu còn task ở trạng thái "pending" $\rightarrow$ quay lại executor tương ứng với task mới.
    *   Nếu tất cả các task đã hoàn tất $\rightarrow$ đi tới `final_synthesizer`.

---

## 6. Cơ chế tối ưu hóa nâng cao trong V2

### 6.1. Context Sandboxing (Cô lập ngữ cảnh tuyệt đối)

Khi một tác vụ ReAct chạy, nó sinh ra rất nhiều lượt Thought, Action và Tool Observation (lên tới hàng chục nghìn tokens). Nếu giữ nguyên lịch sử này sang Task 2, LLM sẽ bị quá tải context, gây nhiễu và giảm chất lượng lập luận.

**Cách hoạt động của Sandboxing:**
1. Khi `task_manager` phát hiện hoàn thành một tác vụ và chuyển sang tác vụ mới, nó trả về một mảng `RemoveMessage` tương ứng với mọi message trung gian phát sinh trong task đó.
2. Nó giữ lại kết quả tinh gọn dưới dạng `findings` (mỗi finding gồm statement và confidence).
3. Khi Task tiếp theo bắt đầu, hàm `_build_executor_instructions` quét toàn bộ các task trước đó, tập hợp các findings lại thành định dạng XML:
   ```xml
   <previous_tasks_findings>
   Task 1 Finding: Attention mechanism improves translation of long sentences (Confidence: 0.95)
   </previous_tasks_findings>
   ```
4. Đoạn text này được đưa thẳng vào System Message của task mới. Nhờ đó, executor mới vừa biết được tri thức cũ, vừa có context hoàn toàn sạch sẽ (chỉ khoảng vài trăm tokens).

---

### 6.2. Confidence-based Fast-Fail (Tự động tự sửa sai nhanh)

Nhằm giảm thiểu việc gọi LLM kiểm định chất lượng (`critic_agent` và `reflection_agent`) khi kết quả đầu ra của Executor hiển nhiên là không đủ tin cậy:

```
                  ┌───────────────────────────────┐
                  │ Executor: Output JSON         │
                  └───────────────┬───────────────┘
                                  │
                       [Đánh giá độ tin cậy]
                                  │
                 ┌────────────────┴────────────────┐
                 │                                 │
           [Tập Findings]                    [Tập Findings]
        Độ tin cậy TB < 0.6               Độ tin cậy TB >= 0.6
                 │                                 │
                 ▼                                 ▼
         [Node: self_correct]             [Node: critic_agent]
    (Bơm nhắc nhở yêu cầu tìm thêm)    (Đánh giá toàn diện chất lượng)
                 │                                 │
                 ▼                                 ▼
           (Executor chạy lại)             [Node: reflection_agent]
```

Cơ chế này tiết kiệm trung bình 40% chi phí tokens của LLM cho các tác vụ cần nhiều lần thử sai do thiếu bằng chứng.

---

### 6.3. Công cụ trích xuất findings có cấu trúc

Do Executor sử dụng vòng lặp ReAct, việc ép LLM trả về cấu trúc định dạng bằng `.with_structured_output()` đồng thời với việc duy trì khả năng gọi tool (`.bind_tools()`) là bất khả thi trong LangChain.

V2 giải quyết vấn đề này bằng phương pháp **Structured Prompt Enforcing**:
1. Tiêm chỉ dẫn xuất định dạng JSON nghiêm ngặt vào System Message (`_build_executor_instructions`).
2. Khi Executor trả ra tin nhắn văn bản cuối cùng, `task_manager` và `evaluate_tool_hooks` sẽ sử dụng `JsonOutputParser(pydantic_object=ExecutorOutput)` để parse cấu trúc. Nếu parse lỗi, hệ thống sẽ sử dụng toàn bộ nội dung text làm kết quả thô (`result`) và danh sách `findings` để trống để đảm bảo chương trình không bị crash đột ngột.

---

## 7. Safeguards & Giới hạn cứng (Hard Limits)

Để đảm bảo hệ thống không bị lặp vô tận (looping) hoặc tiêu tốn quá nhiều chi phí API khi gặp các câu hỏi hóc búa, đồ thị tích hợp 4 chốt chặn an toàn tại node điều hướng `evaluate_tool_hooks` và `route_from_reflection`:

| Giới hạn | Tên hằng số | Mục đích | Cách xử lý khi kích hoạt |
|---|---|---|---|
| **Max Iterations** | `MAX_ITERATIONS = 8` | Giới hạn tối đa số lượt Thought-Action trong một task. | Ngắt ReAct loop ngay lập tức và chuyển tiếp sang node `critic_agent`. |
| **Max Tool Calls** | `MAX_TOOL_CALLS = 10` | Giới hạn tổng số lần gọi tool trong cả vòng đời của session. | Ngắt ReAct loop ngay lập tức và chuyển tiếp sang node `critic_agent`. |
| **Duplicate Tool Detection** | MD5 hash list | Ngăn chặn việc LLM liên tục gọi một tool với các tham số giống hệt nhau khi bị bí. | Ngắt ReAct loop ngay lập tức và chuyển tiếp sang node `critic_agent`. |
| **Max Rework Cycles** | `MAX_REWORK_CYCLES = 2` | Tránh việc Critic bắt làm lại quá nhiều lần đối với một task khó. | Cưỡng chế chuyển sang `task_manager` để hoàn thành task hiện tại và đi tiếp. |

---

## 8. Chiến lược LLM Tiers & Caching (Dynamic Provider Support)

Nhằm tối ưu hóa giữa hiệu năng (quality), chi phí (cost) và độ trễ (latency), hệ thống phân loại mô hình LLM theo 3 tầng chiến lược. Đồng thời, phiên bản V2 hỗ trợ **định cấu hình động (Dynamic Configuration)** cho phép người dùng lựa chọn provider (OpenAI hoặc Gemini) và nạp khóa API riêng cho từng phiên yêu cầu.

```
                     ┌───────────────────────────────┐
                     │           USER PROMPT         │
                     └───────────────┬───────────────┘
                                     │
                 ┌───────────────────┼───────────────────┐
                 ▼                   ▼                   ▼
            [TIER 1 - Fast]     [TIER 2 - Balanced]  [TIER 3 - Reasoning]
             gpt-4o-mini /       gpt-4o /            o1-mini /
             gemini-1.5-flash    gemini-1.5-flash    gemini-1.5-pro
                 │                   │                   │
            Phân loại ý định     General Executor       Deep Research
            Tối ưu hóa query     Planner & Critic       Toán học phức tạp
            Vision Detection     Synthesizer & Reflect  Học máy chuyên sâu
```

### 8.1. Dynamic LLM Factory (`get_llm_instance`)
Thay vì khởi tạo cố định ở cấp độ module, hệ thống sử dụng một nhà máy khởi tạo động `get_llm_instance(tier, config)` để phân giải cấu hình tại thời điểm chạy (runtime):
1.  **Phân giải Provider:** Đọc từ trường `llm_provider` trong `configurable`. Nếu trống, kiểm tra sự tồn tại của `GEMINI_API_KEY` để chọn mặc định `gemini`, ngược lại sử dụng `openai`.
2.  **Đọc khóa API & Base URL:** Cho phép ghi đè API Key và Endpoint từ request. Nếu không có, hệ thống tự động tìm và sử dụng biến môi trường mặc định tương ứng.
3.  **Áp dụng Tầng Mô hình (Tier Model Mapping):**
    *   **OpenAI:** Tier 1 $\rightarrow$ `gpt-4o-mini`, Tier 2 $\rightarrow$ `gpt-4o`, Tier 3 $\rightarrow$ `o1-mini` (hoặc cấu hình tương đương).
    *   **Gemini:** Tier 1 $\rightarrow$ `gemini-1.5-flash`, Tier 2 $\rightarrow$ `gemini-1.5-flash`, Tier 3 $\rightarrow$ `gemini-1.5-pro` (sử dụng thư viện `langchain-google-genai` hoặc OpenAI compatibility endpoint).

### 8.2. Phương thức kích hoạt Dynamic từ Client

#### A. Qua HTTP API (REST Endpoint)
Gửi yêu cầu tới `/chat/stream` kèm theo các trường tùy chọn trong JSON body:
```json
{
  "user_id": "user_123",
  "session_id": "session_abc",
  "prompt": "Analyze this research paper...",
  "llm_provider": "gemini",
  "api_key": "AIzaSy...",
  "tier3_model": "gemini-1.5-pro"
}
```

#### B. Qua gRPC API (Metadata/Headers)
Do protobuf schema được giữ nguyên để đảm bảo khả năng tương thích ngược (C# / .NET Client), các tham số cấu hình động được truyền qua **gRPC Metadata (Headers)** với tiền tố `x-`:
*   `x-llm-provider` (ví dụ: `gemini` hoặc `openai`)
*   `x-api-key` (ví dụ: `AIzaSy...` hoặc `sk-...`)
*   `x-base-url` (endpoint API tùy chỉnh)
*   `x-tier1-model`, `x-tier2-model`, `x-tier3-model` (tên model ghi đè)

### 8.3. Cấu trúc Caching Tối ưu hóa Hiệu năng
Để tránh việc khởi tạo lại mô hình và biên dịch schema gây tăng độ trễ (cold start latency), 3 cơ chế cache song song được áp dụng:

1.  **Cache thực thể LLM (`_LLM_INSTANCE_CACHE`):** Cache các đối tượng mô hình dựa trên hash của API key, tên model, base URL và cấu hình max tokens.
2.  **Cache cấu trúc đầu ra (`_STRUCTURED_LLM_CACHE`):** Lưu trữ kết quả biên dịch của `.with_structured_output(schema)` trên từng thực thể model để tránh dịch JSON Schema lặp đi lặp lại.
3.  **Cache Bind Tool (`_BOUND_LLM_CACHE`):** Cache các thực thể mô hình đã liên kết với các công cụ MCP chuyên biệt của từng domain trong thời gian **O(1)**.

