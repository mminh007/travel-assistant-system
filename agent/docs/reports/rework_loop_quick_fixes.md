# 🔍 Đánh Giá: Fix Nhanh Rework Loop Trước Sprint Ragas

> **Bối cảnh:** Hệ thống hiện tại dùng Rework Loop đồng bộ trên hot-path.
> Sprint tiếp theo sẽ tích hợp Ragas + phân tầng hot-patch evaluation.
> Mục tiêu hiện tại: **Fix những gì có thể, không phá vỡ system.**

---

## Tổng Quan Vấn Đề

| # | Vấn đề | Nguồn gốc | Mức độ ảnh hưởng | Fix được ngay? |
|---|---|---|:---:|:---:|
| 1 | Rework loop "mù" — không inject `evaluator_notes` | §3.2 arch report | 🔴 Cao | ✅ **Đã fix** |
| 2 | `fact_check_feedback` bị overwrite | §3.3 arch report | 🟡 Trung bình | ✅ **Đã fix** |
| 3 | Fact-checker chỉ verify nội lực (không verify thực tế) | §3.3 arch report | 🔴 Cao | ⚠️ Giới hạn — xem bên dưới |
| 4 | Evaluator dùng LLM chấm điểm chính mình | §3.4 arch report | 🟡 Trung bình | ⚠️ Cải thiện được một phần |
| 5 | `max_rework_cycles=2` không có fallback template | §4 eval doc | 🟡 Trung bình | ✅ Fix được ngay |
| 6 | Không có deterministic checks trước LLM fact-checker | §5.6 arch report | 🟢 Low | ✅ Fix được ngay |

---

## ✅ Có Thể Fix Ngay (Không Ảnh Hưởng System)

### Fix A — Fallback Template Khi Hết Rework Cycles (Priority: 🔴)

**Vấn đề hiện tại:**
Khi `rework_count >= max_rework_cycles` và response vẫn deficient, hệ thống set `forced_accept=True` và trả response kém chất lượng ra user. Không có fallback an toàn.

Theo `§4 llm_evaluation_and_guardrails.md`:
> *"Nếu lần retry thứ 2 vẫn không qua bài kiểm tra, trả về câu trả lời an toàn đã được soạn sẵn (Fallback Template)"*

**Fix đề xuất** — trong `node_evaluator_agent()`, khi `forced_accept=True`:

```python
# app/graph/nodes/evaluator.py

REWORK_FALLBACK_TEMPLATE = (
    "Tôi đã cố gắng thu thập thông tin cho yêu cầu của bạn, "
    "nhưng chưa thể xác nhận đầy đủ độ chính xác. "
    "Dưới đây là những gì tôi tìm được — vui lòng kiểm tra lại trước khi quyết định:\n\n"
    "{best_effort_content}"
)

if effective_needs_rework and rework_limit_reached:
    _forced_accept = True
    # Thêm: wrap content trong fallback template thay vì pass raw
    best_effort = state.get("raw_executor_output", "")
    evaluation.feedback = REWORK_FALLBACK_TEMPLATE.format(
        best_effort_content=best_effort
    )
```

**Mức độ thay đổi:** Chỉ sửa `evaluator.py` — không đụng workflow/state/graph.

---

### Fix B — Hardcode Scoring Rubric Vào Evaluator Prompt (Priority: 🟡)

**Vấn đề hiện tại (§3.4):**
LLM chấm 1-10 hoàn toàn chủ quan — không có ground truth, không calibrated.

**Fix đề xuất** — Inject rubric cứng vào `evaluation_prompt`:

```python
# app/graph/nodes/evaluator.py — node_evaluator_agent()

SCORING_RUBRIC = """
SCORING RUBRIC — Use these exact definitions, NOT intuition:

tool_quality_score:
  10 = All needed tools called, results complete and directly relevant
   7 = Most tools called, minor gaps in returned data
   4 = Missing key tool calls, significant data gaps
   1 = No relevant tools called at all

evidence_quality_score:
  10 = Every claim backed by concrete tool observation (price/date/name cited)
   7 = Most claims backed, minor unsupported assertions
   4 = Many claims ungrounded or vague
   1 = Pure hallucination, no tool evidence

citation_quality_score:
  10 = Sources explicitly named for all facts
   7 = Sources named for key facts
   4 = Sources rarely mentioned
   1 = No citations at all

freshness_score:
  10 = Data retrieved live from tools in this session
   7 = Mix of live data and cached/known facts
   4 = Mostly parametric memory, few tool calls
   1 = Entirely from parametric memory, no retrieval
"""

evaluation_prompt = (
    f"You are the EVALUATOR_AGENT.\n"
    f"{SCORING_RUBRIC}\n\n"   # ← inject rubric
    f"MASTER OBJECTIVE: {objective}\n\n"
    # ... rest unchanged
)
```

**Lợi ích:** Scores nhất quán hơn giữa các runs, có thể dùng làm baseline cho Langfuse trend analysis ngay từ bây giờ.

**Mức độ thay đổi:** Chỉ sửa prompt string trong `evaluator.py` — zero risk.

---

### Fix C — Deterministic Pre-checks Trước LLM Fact-Checker (Priority: 🟢)

**Vấn đề hiện tại:**
Fact-checker gọi Tier-1 LLM cho MỌI request kể cả những lỗi format/thiếu field có thể phát hiện bằng code thuần.

**Fix đề xuất** — thêm guard ngay đầu `node_fact_checker()`:

```python
# app/graph/nodes/evaluator.py — node_fact_checker()

def _run_deterministic_checks(findings: list) -> list[str]:
    """
    Tầng 1 — Deterministic checks (<1ms).
    Returns list of violation strings, empty = pass.
    """
    violations = []
    for f in findings:
        content = f.get("content", "")
        # Check 1: Giá âm hoặc bất thường
        import re
        prices = re.findall(r'\b(\d[\d,\.]+)\s*(VND|USD|đ|\$)', content, re.IGNORECASE)
        for price_str, _ in prices:
            price = float(price_str.replace(",", "").replace(".", ""))
            if price <= 0:
                violations.append(f"Invalid price <= 0: {price_str}")

        # Check 2: Ngày trong quá khứ cho booking
        import re
        dates = re.findall(r'\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b', content)
        from datetime import date
        for d, m, y in dates:
            try:
                parsed = date(int(y), int(m), int(d))
                if parsed < date.today():
                    violations.append(f"Past date found for booking: {d}/{m}/{y}")
            except ValueError:
                violations.append(f"Invalid date format: {d}/{m}/{y}")

    return violations

# Trong node_fact_checker():
deterministic_issues = _run_deterministic_checks(extracted_findings)
if deterministic_issues:
    logger.warning(f"⚠️ [DETERMINISTIC CHECK] Issues found: {deterministic_issues}")
    # Vẫn tiếp tục gọi LLM fact-checker nhưng đã có thêm signal
    # (hoặc có thể skip LLM nếu issues quá rõ ràng)
```

**Mức độ thay đổi:** Additive — chỉ thêm helper function, không sửa flow.

---

## ⚠️ Giới Hạn — Không Thể Fix Hoàn Toàn Lúc Này

### Vấn đề 3: Fact-Checker Chỉ Verify Nội Lực

**Tại sao không thể fix ngay:**

```
Fact-checker verify: "Agent nói đúng những gì tool trả về?"
                     ✅ Có thể check
Nhưng KHÔNG verify: "Tool data có đúng thực tế không?"
                     ❌ Cần external ground truth
```

Để verify tính chính xác tuyệt đối của tool data, cần:
- External API cross-check (Google Maps, Booking.com, etc.)
- Golden dataset làm ground truth → **đây là việc của Ragas sprint**
- Đây là bài toán **Data Grounding**, không phải code fix

> [!IMPORTANT]
> Cách tiếp cận đúng (§4 — Shift-Left): Thay vì check sau khi sinh, inject dữ liệu chuẩn xác **vào context trước khi LLM generate**. Đây là kiến trúc thay đổi lớn — để sprint Ragas.

### Vấn đề 4: Evaluator Chấm Điểm Chính Mình

**Tại sao chỉ cải thiện được một phần:**
- Fix B (Scoring Rubric) giúp tăng tính nhất quán
- Nhưng bài toán LLM-judge-LLM không thể giải hoàn toàn nếu không có ground truth
- **Giải pháp thực sự:** Ragas `AnswerRelevance` + `CustomRubrics` với Golden Dataset → sprint tiếp theo

---

## 📊 Tóm Tắt Prioritized Action

```
Sprint hiện tại (Không phá system):
┌─────────────────────────────────────────────────────────────┐
│  ✅ DONE   Fix A-prime: Inject evaluator_notes vào executor  │
│  ✅ DONE   Fix A-prime: fact_check_feedback field riêng      │
│  🔲 TODO   Fix A: Fallback Template khi forced_accept=True   │
│  🔲 TODO   Fix B: Hardcode Scoring Rubric vào evaluator      │
│  🔲 TODO   Fix C: Deterministic pre-checks (price/date)      │
└─────────────────────────────────────────────────────────────┘

Sprint tiếp theo (Ragas + phân tầng):
┌─────────────────────────────────────────────────────────────┐
│  📋 PLAN   Async shadow eval qua RabbitMQ                   │
│  📋 PLAN   Skip evaluator cho complexity=low                │
│  📋 PLAN   Ragas Golden Dataset CI/CD pipeline              │
│  📋 PLAN   Shift-Left: data grounding trước generation      │
└─────────────────────────────────────────────────────────────┘
```

---

> **Nguyên tắc:** Những fix ở sprint này chỉ sửa **bên trong node** (prompt, return value, helper function). Không đụng đến `workflow.py` (graph edges), `state.py` schema (đã thêm 1 field nhỏ), hay bất kỳ external dependency nào.
