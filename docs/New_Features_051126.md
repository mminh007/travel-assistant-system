# Sprint Plans: Tiered Evaluation Architecture

> **Context:** Migrating from synchronous rework loop (10–22s hot-path) to a
> tiered async evaluation model. Two independent sprints, each deployable alone.

---

## Sprint A — Fast & Safe Hot-Path

> **Goal:** Remove blocking eval from hot-path → user response in 4–7s.
> Replace with Guardrails AI (online, lightweight) + async shadow eval (RabbitMQ).

### Architecture After Sprint A

```
input_guardrail
     │
     ├─[low]──→ direct_executor_init ─┐
     └─[med/high]──→ planner ─────────┤
                                       ▼
                              travel_react_agent (ReAct loop)
                                       │
                              evaluate_tool_hooks (safeguards)
                                       │
                              finding_extractor
                                       │
                    ┌──────────────────┼──────────────────────┐
                    │                  │ fire-and-forget       │
                    │            [complexity != low]           │
                    │          publish → RabbitMQ queue        │
                    │          "eval.shadow"                   │
                    │                  │                       │
                    │        [async background worker]         │
                    │        fact_checker                      │
                    │        evaluator_agent                   │
                    │        → Langfuse scores                 │
                    │                                          │
                    ▼                                          │
           [Guardrails AI — 100-300ms]                        │
           Validator 1: Travel domain scope                   │
           Validator 2: Response format / length              │
           Validator 3: Safety / no toxic content             │
           → Fail: auto re-ask 1 lần (không loop)            │
           → Pass: continue                                   │
                    │                                          │
                    ▼                                          │
           task_manager → final_synthesizer                   │
                               │                              │
                          + disclaimer footer                 │
                               ▼
                        STREAM TO USER ✅
```

---

### Proposed Changes

---

#### Component A1 — Graph Restructure

##### [MODIFY] [workflow.py](file:///C:/Users/tuanm/OneDrive/project2/Booking/agent/app/graph/workflow.py)

**Xóa khỏi graph:**
```python
# REMOVE — sync blocking eval pipeline:
workflow.add_node("fact_checker", node_fact_checker)
workflow.add_node("evaluator_agent", node_evaluator_agent)
workflow.add_edge("finding_extractor", "fact_checker")       # → thay bằng guardrails
workflow.add_edge("fact_checker", "evaluator_agent")
workflow.add_conditional_edges("evaluator_agent", route_from_evaluator, {...})

# REMOVE — rework loop constants/functions:
MAX_REWORK_CYCLES = ...
route_from_evaluator()
```

**Thêm vào graph:**
```python
# ADD — Guardrails AI node sau finding_extractor:
workflow.add_node("output_guardrail", node_output_guardrail)
workflow.add_edge("finding_extractor", "output_guardrail")
workflow.add_conditional_edges(
    "output_guardrail",
    route_from_output_guardrail,
    {
        "reask": "travel_react_agent",   # 1 lần re-ask nếu validator fail
        "pass":  "task_manager"          # tiếp tục nếu pass
    }
)
```

**Xóa import:**
```python
# REMOVE từ import block:
from app.graph.nodes import (
    ...
    node_evaluator_agent,   # ← xóa (move to async worker)
    node_fact_checker,      # ← xóa (move to async worker)
    ...
)
```

---

#### Component A2 — Guardrails AI Node (mới)

##### [NEW] `agent/app/graph/nodes/output_guardrail.py`

Node mới thay thế vai trò "blocking quality gate" của evaluator_agent trên hot-path:

```python
# app/graph/nodes/output_guardrail.py
from guardrails import Guard
from guardrails.hub import ToxicLanguage, ValidLength, RestrictToTopic

# Define guard with travel-specific validators
_travel_guard = Guard().use_many(
    RestrictToTopic(
        valid_topics=["travel", "hotel", "flight", "itinerary", "tourism"],
        disable_classifier=False,
        on_fail="reask"
    ),
    ValidLength(min=50, max=4000, on_fail="reask"),
    ToxicLanguage(threshold=0.5, on_fail="exception"),
)

async def node_output_guardrail(state: AgentState, config: RunnableConfig = None):
    """
    Node: OUTPUT_GUARDRAIL (replaces blocking evaluator on hot-path).
    Runs Guardrails AI validators synchronously (~100-300ms).
    On fail: sets reask_count + returns signal for single re-ask.
    On pass: continues to task_manager.
    """
    raw_output = state.get("raw_executor_output", "")
    reask_count = state.get("reask_count", 0)

    # Hard limit: only allow 1 re-ask (not a loop)
    if reask_count >= 1:
        logger.warning("[OutputGuardrail] Re-ask limit reached. Passing through.")
        return {"guardrail_passed": True}

    try:
        _travel_guard.validate(raw_output)
        logger.info("[OutputGuardrail] ✅ All validators passed.")
        return {"guardrail_passed": True, "reask_count": reask_count}
    except Exception as e:
        logger.warning(f"[OutputGuardrail] ⚠️ Validator failed: {e}. Triggering re-ask.")
        return {"guardrail_passed": False, "reask_count": reask_count + 1}

def route_from_output_guardrail(state: AgentState) -> str:
    if not state.get("guardrail_passed", True):
        return "reask"
    return "pass"
```

##### [MODIFY] [state.py](file:///C:/Users/tuanm/OneDrive/project2/Booking/agent/app/graph/state.py)

```python
# ADD fields:
guardrail_passed: Optional[bool]   # Set by node_output_guardrail
reask_count: int                   # Tracks re-ask attempts (max 1)

# REMOVE fields (rework loop no longer exists):
needs_rework: Optional[bool]
rework_count: int
forced_accept: Optional[bool]
```

---

#### Component A3 — Async Shadow Eval Publisher

> [!NOTE]
> `rabbitmq_publisher.py` đã tồn tại tại
> [rabbitmq_publisher.py](file:///C:/Users/tuanm/OneDrive/project2/Booking/agent/app/services/background_tasks/rabbitmq_publisher.py).
> Chỉ cần thêm hàm publish mới cho shadow eval, không cần tạo file mới.

##### [MODIFY] `agent/app/services/background_tasks/rabbitmq_publisher.py`

```python
# Thêm hàm mới — không sửa hàm cũ publish_extraction_task:

EVAL_SHADOW_QUEUE = "eval.shadow"

async def publish_shadow_eval(
    session_id: str,
    trace_id: str,
    objective: str,
    executor_output: str,
    findings: list,
    tool_observations: list,
    complexity: str,
) -> None:
    """
    Fire-and-forget: publishes evaluation payload to the async shadow eval queue.
    Called from node_finding_extractor after extraction completes.
    Skipped for complexity=low to reduce worker overhead.
    """
    if complexity == "low":
        logger.debug("[ShadowEval] Skipping for low-complexity query.")
        return

    payload = {
        "codename_process": "ShadowEvalProcess",
        "session_id": session_id,
        "trace_id": trace_id,
        "objective": objective,
        "executor_output": executor_output,
        "findings": findings,
        "tool_observations": tool_observations[:10],  # cap to avoid huge payloads
    }

    try:
        connection = await get_connection()
        channel = await connection.channel()
        await channel.declare_queue(EVAL_SHADOW_QUEUE, durable=True)
        await channel.default_exchange.publish(
            aio_pika.Message(
                body=json.dumps(payload, ensure_ascii=False).encode(),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT
            ),
            routing_key=EVAL_SHADOW_QUEUE,
        )
        logger.info(f"[ShadowEval] Published eval event for session={session_id}")
        await channel.close()
    except Exception as e:
        # Non-critical: shadow eval failure must never break the hot-path
        logger.error(f"[ShadowEval] Publish failed (non-fatal): {e}")
```

##### [MODIFY] [extractor.py](file:///C:/Users/tuanm/OneDrive/project2/Booking/agent/app/graph/nodes/extractor.py)

```python
# Thêm vào cuối node_finding_extractor(), sau return statement cũ:
import asyncio
from app.services.background_tasks.rabbitmq_publisher import publish_shadow_eval

# Fire-and-forget: does NOT block hot-path
tool_observations = [
    msg.content for msg in state["messages"]
    if getattr(msg, "type", "") == "tool"
]
asyncio.create_task(
    publish_shadow_eval(
        session_id=state.get("session_id", ""),
        trace_id=state.get("langfuse_trace_id", ""),
        objective=state.get("objective", ""),
        executor_output=raw_summary,
        findings=findings,
        tool_observations=tool_observations,
        complexity=state.get("complexity", "medium"),
    )
)
```

---

#### Component A4 — Async Shadow Eval Worker

##### [NEW] `agent/app/services/background_tasks/shadow_eval_worker.py`

Consumer chạy độc lập, subscribe queue `eval.shadow`. Tái sử dụng
`node_fact_checker` và `node_evaluator_agent` như plain async functions
(không phải graph nodes):

```python
# app/services/background_tasks/shadow_eval_worker.py
import aio_pika, json
from app.graph.nodes.evaluator import node_fact_checker, node_evaluator_agent
from app.core.settings import settings
from app.core.logger import setup_app_logger

logger = setup_app_logger("ShadowEvalWorker")

async def process_eval_event(payload: dict) -> None:
    """Runs fact_checker + evaluator_agent async on shadow eval payload."""
    # Build a minimal state dict (not a full graph run)
    mock_state = {
        "messages": [_rebuild_tool_messages(payload["tool_observations"])],
        "extracted_findings": payload["findings"],
        "raw_executor_output": payload["executor_output"],
        "objective": payload["objective"],
        "rework_count": 0,
        "action_history": [],
    }
    # Run fact checker
    fc_result = await node_fact_checker(mock_state)
    mock_state.update(fc_result)
    # Run evaluator
    eval_result = await node_evaluator_agent(mock_state)

    logger.info(
        f"[ShadowEval] session={payload['session_id']} "
        f"scores: tools={eval_result.get('tool_quality_score')} "
        f"evidence={eval_result.get('evidence_quality_score')}"
    )
    # Scores auto-forwarded to Langfuse via existing emit mechanism

async def run_shadow_eval_worker() -> None:
    """Main consumer loop — registered in worker_main.py."""
    connection = await aio_pika.connect_robust(settings.rabbitmq.url)
    channel = await connection.channel()
    queue = await channel.declare_queue("eval.shadow", durable=True)

    async with queue.iterator() as q:
        async for message in q:
            async with message.process():
                try:
                    payload = json.loads(message.body.decode())
                    await process_eval_event(payload)
                except Exception as e:
                    logger.error(f"[ShadowEvalWorker] Error: {e}")
```

##### [MODIFY] `agent/app/worker_main.py`

```python
# Thêm shadow eval worker vào startup tasks (cùng file với các worker hiện tại):
from app.services.background_tasks.shadow_eval_worker import run_shadow_eval_worker

# Trong startup coroutines:
asyncio.create_task(run_shadow_eval_worker())
```

---

#### Component A5 — Disclaimer Footer

##### [MODIFY] [synthesizer.py](file:///C:/Users/tuanm/OneDrive/project2/Booking/agent/app/graph/nodes/synthesizer.py)

```python
# Thêm vào cuối node_final_synthesizer(), trước return:
_RESPONSE_DISCLAIMER = (
    "\n\n---\n"
    "> ⚠️ **AI-generated content.** Please verify critical details "
    "(prices, dates, availability) with official sources before making decisions."
)

# Append disclaimer to final response content:
if final_response and hasattr(final_response, "content"):
    final_response.content = final_response.content + _RESPONSE_DISCLAIMER
```

---

### Sprint A — Verification Plan

#### Automated Tests
```bash
# Unit: shadow eval publisher (mock RabbitMQ)
pytest tests/unit/test_shadow_eval_publisher.py

# Unit: output_guardrail validators pass/fail/reask logic
pytest tests/unit/test_output_guardrail.py

# Integration: graph no longer contains fact_checker/evaluator_agent nodes
pytest tests/integration/test_workflow_graph.py -k "test_nodes_registered"

# E2E: measure response latency improvement
pytest tests/e2e/test_latency_regression.py
```

#### Manual Verification
- [ ] RabbitMQ management UI: queue `eval.shadow` nhận messages sau mỗi request
- [ ] Langfuse: eval scores vẫn xuất hiện (qua async worker, chậm hơn vài giây)
- [ ] Response có disclaimer footer
- [ ] P50 latency giảm ≥3s so với baseline

---

### Sprint A — Estimated Effort

| Task | Effort |
|---|---|
| Graph restructure (workflow.py) | 1 ngày |
| Guardrails AI node + validators | 2 ngày |
| Shadow eval publisher (extend rabbitmq_publisher.py) | 1 ngày |
| Shadow eval worker (shadow_eval_worker.py) | 2 ngày |
| Disclaimer footer + state cleanup | 0.5 ngày |
| Tests + integration verification | 2 ngày |
| **Tổng** | **~8.5 ngày** |

---
---

## Sprint B — Quality Intelligence

> **Goal:** Catch quality regressions before they reach production.
> Ragas CI/CD pipeline + Shift-Left data grounding để giảm hallucination tại nguồn.

### Architecture After Sprint B

```
Sprint A hot-path (giữ nguyên)
     +
Shift-Left node chạy TRƯỚC travel_react_agent:
  planner → data_grounding_node → travel_react_agent
                │
     Pre-fetch data từ MCP tools (hotel, place search)
     Inject vào context: "Only use data from <grounded_data>"
     → Hallucination giảm 85-90%

Ragas chạy 2 nơi:
  1. CI/CD pipeline → mỗi PR thay đổi prompt/model/node
  2. Shadow eval worker (5% sampling production traffic)
```

---

### Proposed Changes

---

#### Component B1 — Shift-Left Data Grounding Node

##### [NEW] `agent/app/graph/nodes/data_grounding.py`

```python
# app/graph/nodes/data_grounding.py
"""
Shift-Left: pre-fetch relevant data BEFORE LLM generation.
Principle (§4 llm_evaluation_and_guardrails.md):
  "Provide accurate data upfront → LLM organizes, not hallucinates."
  "Hallucination drops 85-90% without any post-generation check."

Applies to: hotel_booking, itinerary_planning
Pass-through for: travel_faq, system_navigation_faq, flight_booking (future)
"""
async def node_data_grounding(state: AgentState, config: RunnableConfig = None):
    intent = state.get("intent_category", "")
    GROUNDING_INTENTS = {"hotel_booking", "itinerary_planning"}

    if intent not in GROUNDING_INTENTS:
        return {}   # Pass-through — no grounding needed

    objective = state.get("objective", "")
    # 1. Extract key entities from objective using Tier-1 LLM
    entities = await _extract_entities(objective, config)
    # location, checkin_date, checkout_date, num_guests, budget_range

    # 2. Pre-call relevant MCP tools
    grounded_data = {}
    if entities.get("location"):
        hotel_results = await _call_hotel_search_tool(entities, config)
        grounded_data["hotels"] = hotel_results

        place_results = await _call_place_search_tool(entities, config)
        grounded_data["places"] = place_results

    if not grounded_data:
        return {}   # Grounding failed — fall through, executor uses tools normally

    logger.info(f"[DataGrounding] Pre-fetched {sum(len(v) for v in grounded_data.values())} items.")
    return {"grounded_context": grounded_data}
```

##### [MODIFY] [workflow.py](file:///C:/Users/tuanm/OneDrive/project2/Booking/agent/app/graph/workflow.py)

```python
# ADD grounding node between planner and executor:
from app.graph.nodes.data_grounding import node_data_grounding

workflow.add_node("data_grounding", node_data_grounding)
workflow.add_edge("planner", "data_grounding")            # was: "planner" → "travel_react_agent"
workflow.add_edge("data_grounding", "travel_react_agent")
# direct_executor_init (low complexity) skips grounding — no change needed
```

##### [MODIFY] [executor.py](file:///C:/Users/tuanm/OneDrive/project2/Booking/agent/app/graph/nodes/executor.py)

```python
# Inject grounded_context into system prompt when available:
grounded_context = state.get("grounded_context")
if grounded_context:
    system_content += (
        f"\n\n<grounded_data>\n"
        f"The following data was pre-fetched and is VERIFIED. "
        f"You MUST use ONLY these sources for the facts listed. "
        f"Do NOT invent hotels, places, or prices outside this list.\n"
        f"{json.dumps(grounded_context, ensure_ascii=False, indent=2)}\n"
        f"</grounded_data>\n"
    )
```

##### [MODIFY] [state.py](file:///C:/Users/tuanm/OneDrive/project2/Booking/agent/app/graph/state.py)

```python
# ADD:
grounded_context: Optional[Dict[str, Any]]  # Pre-fetched data from data_grounding_node
```

---

#### Component B2 — Ragas CI/CD Pipeline

##### [NEW] `tests/eval/ragas_runner.py`

```python
# tests/eval/ragas_runner.py
from ragas import evaluate
from ragas.metrics import answer_relevancy
from ragas.metrics.critique import AspectCritique
from datasets import Dataset

travel_completeness = AspectCritique(
    name="travel_completeness",
    definition=(
        "Does the response provide complete, actionable travel information? "
        "It should include: specific location names, estimated prices or ranges, "
        "dates or availability context, and at least one concrete recommendation."
    )
)

travel_accuracy = AspectCritique(
    name="travel_accuracy",
    definition=(
        "Does the response avoid vague or unverifiable claims? "
        "It should not state prices, hotel names, or availability "
        "without clear attribution to a data source."
    )
)

def run_ragas_eval(dataset_path: str) -> dict:
    import json
    with open(dataset_path) as f:
        rows = [json.loads(l) for l in f]

    dataset = Dataset.from_list([{
        "question": r["question"],
        "answer": r["answer"],
        "ground_truth": r.get("ground_truth", ""),
    } for r in rows])

    result = evaluate(
        dataset,
        metrics=[answer_relevancy, travel_completeness, travel_accuracy],
    )
    return result
```

##### [NEW] `tests/eval/golden_dataset.jsonl`

Tập dữ liệu mẫu — cần verify thủ công trước khi dùng làm ground truth:

```jsonl
{"question": "Khách sạn 3 sao tại Đà Lạt dưới 1 triệu/đêm", "ground_truth": "Response phải đề xuất ít nhất 2 khách sạn cụ thể với giá, địa chỉ, và rating.", "reference_tools": ["hotel_search"]}
{"question": "Lên kế hoạch du lịch Hội An 3 ngày 2 đêm cho 2 người", "ground_truth": "Itinerary đủ 3 ngày, có khách sạn, địa điểm tham quan, ẩm thực, chi phí ước tính.", "reference_tools": ["hotel_search", "place_search"]}
{"question": "So sánh giá vé máy bay Hà Nội - Đà Nẵng tháng 12", "ground_truth": "So sánh ít nhất 2 hãng bay, giá khứ hồi, chú thích thời điểm giá tốt.", "reference_tools": ["flight_search"]}
```

##### [NEW] `.github/workflows/ragas_eval.yml`

```yaml
name: Ragas Quality Gate

on:
  pull_request:
    paths:
      - 'agent/app/graph/nodes/**'
      - 'agent/app/graph/workflow.py'
      - 'agent/app/graph/state.py'
      - 'tests/eval/**'

jobs:
  ragas-quality-gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: pip install ragas datasets openai

      - name: Run Ragas Evaluation
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
        run: |
          python -m pytest tests/eval/test_ragas_quality_gate.py \
            --dataset=tests/eval/golden_dataset.jsonl \
            -v

      - name: Check quality thresholds
        run: |
          python tests/eval/ragas_runner.py \
            --dataset tests/eval/golden_dataset.jsonl \
            --fail-below answer_relevancy=0.75 \
            --fail-below travel_completeness=0.70 \
            --fail-below travel_accuracy=0.72
```

---

#### Component B3 — Ragas Sampling trong Shadow Eval Worker

##### [MODIFY] `agent/app/services/background_tasks/shadow_eval_worker.py`

```python
# Thêm vào process_eval_event() — sau khi evaluator_agent chạy xong:
import hashlib

def _should_sample_for_ragas(session_id: str, rate: float = 0.05) -> bool:
    """Deterministic 5% sampling via MD5 hash — same session always same decision."""
    hash_val = int(hashlib.md5(session_id.encode()).hexdigest(), 16)
    return (hash_val % 100) < int(rate * 100)

async def process_eval_event(payload: dict) -> None:
    # ... existing fact_checker + evaluator_agent logic ...

    # Ragas 5% sampling
    if _should_sample_for_ragas(payload["session_id"]):
        logger.info(f"[Ragas] Sampled session {payload['session_id']} for quality audit.")
        ragas_scores = await run_ragas_on_payload(payload)
        await emit_ragas_scores_to_langfuse(payload["trace_id"], ragas_scores)
```

---

### Sprint B — Verification Plan

#### Automated Tests
```bash
# Unit: data_grounding entity extraction
pytest tests/unit/test_data_grounding.py

# Unit: grounded_context injection into executor system prompt
pytest tests/unit/test_executor_grounding_injection.py

# Ragas quality gate on golden dataset (also runs in CI)
python tests/eval/ragas_runner.py --dataset tests/eval/golden_dataset.jsonl

# Integration: planner → data_grounding → travel_react_agent edge exists
pytest tests/integration/test_workflow_graph.py -k "test_grounding_edge"
```

#### Manual Verification
- [ ] Với query `"Khách sạn Đà Lạt"`: executor nhận `<grounded_data>` trong context
- [ ] Ragas CI pipeline block PR nếu `answer_relevancy < 0.75`
- [ ] Langfuse: Ragas scores xuất hiện cho 5% sessions được sample
- [ ] So sánh hallucination rate trước/sau Shift-Left (manual review 20 responses)

---

### Sprint B — Estimated Effort

| Task | Effort |
|---|---|
| data_grounding_node (entity extraction + tool pre-fetch) | 3 ngày |
| Executor grounded_context injection | 0.5 ngày |
| Golden dataset tạo + verify thủ công | 2 ngày |
| Ragas CI/CD pipeline + GitHub Actions | 1.5 ngày |
| Ragas sampling trong shadow_eval_worker | 1 ngày |
| Tests + integration verification | 2 ngày |
| **Tổng** | **~10 ngày** |

---

## Open Questions — Cần Quyết Định Trước Khi Implement

> [!IMPORTANT]
> **Q1 (Sprint A):** Guardrails AI `RestrictToTopic` validator cần define
> `valid_topics` và chạy một classifier model. Nếu không có GPU local,
> latency có thể tăng lên 300–500ms. Chấp nhận không?
> Nếu không → dùng regex-based validator thay thế (nhanh hơn, kém thông minh hơn).

> [!IMPORTANT]
> **Q2 (Sprint A):** `shadow_eval_worker` deploy như thế nào?
> (A) Chạy cùng process FastAPI (background task trong `worker_main.py`) — đơn giản hơn, chia sẻ resource
> (B) Docker container riêng — isolated, scale độc lập

> [!IMPORTANT]
> **Q3 (Sprint B):** Golden dataset `tests/eval/golden_dataset.jsonl` cần
> ai tạo và review? Nếu dataset sai → Ragas CI gate sẽ fail/pass sai.
> Cần quy trình review rõ ràng trước khi dùng làm quality gate.

> [!NOTE]
> **Q4 (Sprint B):** `node_data_grounding` hiện chỉ áp dụng cho
> `hotel_booking` + `itinerary_planning`. `flight_booking` có cần grounding không?
> (Cần biết MCP tool nào handle flight search.)

---

## Branch Strategy

```
main
 ├── sprint-a/fast-safe-hotpath
 │    ├── feat/guardrails-ai-output-node
 │    ├── feat/async-shadow-eval-rabbitmq
 │    └── refactor/remove-sync-eval-graph
 │
 └── sprint-b/quality-intelligence
      ├── feat/shift-left-data-grounding
      ├── feat/ragas-ci-pipeline
      └── feat/ragas-shadow-sampling
```

Sprint A và B hoàn toàn độc lập — Sprint B có thể bắt đầu song song
sau khi Sprint A đã merge xong phần graph restructure.
