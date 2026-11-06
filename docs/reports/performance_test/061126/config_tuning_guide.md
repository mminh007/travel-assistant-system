# Config Tuning Guide — Travel Agent vLLM Stack
> RTX 3090 (24 GB VRAM) · Co-located: LLM + Embedding · Qwen2.5-7B-AWQ + Qwen3-Embedding-4B

---

## Bức Tranh Toàn Cảnh — 4 Tầng Tham Số

Hệ thống có **4 tầng** kiểm soát concurrency và throughput. Chúng **phải khớp nhau** từ trên xuống dưới, nếu không tầng nào tight hơn sẽ trở thành bottleneck vô hình:

```
┌─────────────────────────────────────────────────────────────┐
│  Tầng 1: vLLM Server  (Vast.ai process)                    │
│  max-num-seqs, max-num-batched-tokens, gpu-memory-util      │
│  → Quyết định GPU chịu được bao nhiêu concurrent sequences │
├─────────────────────────────────────────────────────────────┤
│  Tầng 2: .env  (agent/app boundary)                        │
│  VLLM_MAX_COMPLETION_TOKENS, VLLM_MAX_CONTEXT_TOKENS        │
│  → Quyết định mỗi request "dùng" bao nhiêu KV cache slot  │
├─────────────────────────────────────────────────────────────┤
│  Tầng 3: concurrency.py  (Python asyncio gate)             │
│  TIER1_SEMAPHORE, TIER2_SEMAPHORE                           │
│  → Giới hạn Python app gửi tối đa bao nhiêu LLM call song  │
│    song (không gây queue storm ở vLLM)                      │
├─────────────────────────────────────────────────────────────┤
│  Tầng 4: settings.py NodeTokenLimits  (per-node budget)    │
│  NODE_MAX_TOKENS_*                                          │
│  → Cap output tokens của từng node — tránh một node ăn hết │
│    max_completion_tokens và truncate response               │
└─────────────────────────────────────────────────────────────┘
```

---

## Tầng 1: vLLM Server (`start_awq_kv_fp8.sh`)

### VRAM Budget — RTX 3090 24 GB

```
Tổng VRAM:                    24.0 GB
LLM server  (gpu-util=0.50):  12.0 GB
Embedding   (gpu-util=0.44):  10.6 GB (10.56 GB actual)
CUDA overhead / safety buf:    1.4 GB
─────────────────────────────────────
Còn lại (buffer):             ~0.0 GB  ← TIGHT, không nâng gpu-util thêm
```

> [!CAUTION]
> Tổng `gpu-util` của 2 process là `0.50 + 0.44 = 0.94`. **Không được tăng thêm** — sẽ gây OOM crash cả 2 process.

### Config Hiện Tại vs Khuyến Nghị

| Tham số | Hiện tại | Khuyến nghị | Lý do |
|---|---|---|---|
| `--max-model-len` | 4096 | **4096** ✅ giữ | Vừa đủ cho use-case travel; tăng → KV cache lớn hơn → ít slot hơn |
| `--max-num-seqs` | **16** ❌ | **48** | 16 → queue storm khi 50+ users; 48 cân bằng VRAM KV cache (xem tính toán bên dưới) |
| `--max-num-batched-tokens` | 512 | **2048** | 512 cho throughput thấp; 2048 cho batching hiệu quả hơn khi nhiều sequences cùng lúc |
| `--gpu-memory-utilization` | 0.50 | **0.50** ✅ giữ | Không tăng (co-located với embedding) |
| `--enable-chunked-prefill` | ✅ | **✅ giữ** | Giảm latency spike khi prefill lớn |
| `--enable-prefix-caching` | ✅ | **✅ giữ** | Giúp batching các request cùng system prompt |
| `--enable-auto-tool-choice` | ✅ | **✅ giữ** | Bắt buộc cho ReAct agent |
| `--tool-call-parser` | `hermes` | **`hermes`** ✅ | Qwen2.5 dùng Hermes standard |

### Tại sao `max-num-seqs=48`?

```
KV cache VRAM ≈ 2 × num_layers × num_heads × head_dim × max_seq_len × num_seqs × dtype_bytes
Qwen2.5-7B: 28 layers, 28 heads, head_dim=128, dtype=fp16 (2 bytes)

1 slot KV cache (4096 tokens, fp16) ≈ 28 × 28 × 128 × 4096 × 2 / 1e9 ≈ 0.082 GB

Tổng VRAM cho KV cache khi gpu-util=0.50:
  12.0 GB (tổng) - ~7.5 GB (weights AWQ) - 0.5 GB (CUDA graph) = ~4.0 GB dành cho KV cache
  
4.0 GB / 0.082 GB per slot = ~49 slots  →  max-num-seqs = 48 (buffer nhỏ)
```

> [!TIP]
> Với `max-num-seqs=48` và `max-num-batched-tokens=2048`, vLLM có thể batch nhiều requests ngắn vào 1 lần forward pass → throughput tăng đáng kể mà latency per-token không tăng nhiều.

### File `start_awq_kv_fp8.sh` cập nhật

```bash
vllm serve "$MODEL" \
  --host 0.0.0.0 \
  --port "$PORT" \
  --dtype float16 \
  --quantization awq_marlin \
  --kv-cache-dtype "$KV_DTYPE" \
  --max-model-len 4096 \
  --gpu-memory-utilization "$GPU_UTIL" \     # giữ 0.50
  --enable-chunked-prefill \
  --max-num-batched-tokens 2048 \            # tăng từ 512
  --enable-prefix-caching \
  --max-num-seqs 48 \                        # tăng từ 16
  --enable-auto-tool-choice \
  --tool-call-parser hermes \
  --served-model-name "$MODEL" "$(basename "$MODEL")"
```

---

## Tầng 2: `.env` — Token Budgets

### Mối quan hệ cần đảm bảo

```
VLLM_MAX_CONTEXT_TOKENS  ≤  --max-model-len  (server hard limit)
VLLM_MAX_COMPLETION_TOKENS  ≤  VLLM_MAX_CONTEXT_TOKENS
```

**Hiện tại:**
```env
VLLM_MAX_COMPLETION_TOKENS=1024   # output cap mỗi call
VLLM_MAX_CONTEXT_TOKENS=4096      # = max-model-len của server
```

**Vấn đề:** `VLLM_MAX_CONTEXT_TOKENS=4096` nhưng thực tế mỗi node chỉ dùng ~100 input tokens (theo metric). Input + output per call ≈ 100 + 800 = 900 tokens — rất xa 4096. Điều này tốt: KV cache slot **không bị waste** per request.

**Giữ nguyên các giá trị này.** Chúng đã được tính đúng.

---

## Tầng 3: `concurrency.py` — Asyncio Semaphore

Đây là tầng **hay bị bỏ quên** nhưng quan trọng nhất để ngăn **queue storm**.

### Vấn đề hiện tại

```python
_CONCURRENCY = {
    "vllm": {"tier1": 12, "tier2": 4},  # ← KHÔNG KHỚP với max-num-seqs
}
```

Với `max-num-seqs=16` cũ: `tier1=12 + tier2=4 = 16` → khớp hoàn hảo.

Sau khi tăng `max-num-seqs=48`, semaphore cũ trở nên **quá conservative** — Python app tự giới hạn ở 16 concurrent mặc dù server có thể xử lý 48.

### Công thức tính semaphore

```
Semaphore = Slots dành cho tier đó trên vLLM

Phân bổ slots:
  - Tier 1 (input_guardrail, finding_extractor, fact_checker): lightweight, nhiều calls
  - Tier 2 (travel_react_agent, planner, evaluator): heavy, ít calls hơn

Khuyến nghị phân bổ (tổng = 48):
  Tier 1: 32 slots  (nhiều requests nhỏ, nhanh)
  Tier 2: 16 slots  (ít requests lớn, chậm hơn)
  
  Lưu ý: Tổng semaphore (32+16=48) ≤ max-num-seqs (48) ← QUAN TRỌNG
```

### Cập nhật `concurrency.py`

```python
_CONCURRENCY = {
    "nine_router": {"tier1": 8,  "tier2": 8},
    "vllm":        {"tier1": 32, "tier2": 16},  # khớp với max-num-seqs=48
    "claude":      {"tier1": 4,  "tier2": 2},
}
```

> [!WARNING]
> **Quy tắc bất biến:** `tier1_semaphore + tier2_semaphore ≤ max-num-seqs`.
> Nếu tổng semaphore **vượt** max-num-seqs: app gửi nhiều hơn server xử lý được → requests bị queue ở server → latency tăng thay vì giảm.

---

## Tầng 4: `NodeTokenLimits` — Per-Node Output Budget

### Vấn đề hiện tại

```python
class NodeTokenLimits(BaseSettings):
    input_guardrail:    int = 500
    support_agent:      int = 500   # ← cần điều tra: metric cho thấy latency cao bất thường
    planner_agent:      int = 600
    travel_react_agent: int = 800   # ← điểm cần chú ý
    finding_extractor:  int = 400
    fact_checker:       int = 1000  # ← chỉ dùng trong shadow eval (async), không impact hot-path
    evaluator_agent:    int = 400   # ← chỉ dùng trong shadow eval (async)
    final_synthesizer:  int = 1000
    clarification_agent:int = 200
```

### Mối quan hệ cần đảm bảo

```
Mỗi NODE_MAX_TOKENS_* ≤ VLLM_MAX_COMPLETION_TOKENS (1024)
Tổng tokens per request ≈ max(node budgets trên hot-path) ≤ VLLM_MAX_CONTEXT_TOKENS (4096)
```

**Hot-path token flow** (phân tích từ metric - output ~30 tokens/node):
```
input_guardrail     → ~15 tokens output  (budget: 500) ← budget dư thừa nhiều
planner/direct      → ~25 tokens output  (budget: 600) ← dư thừa
travel_react_agent  → ~30-35 tokens output (budget: 800) ← hợp lý cho ReAct
finding_extractor   → ~20 tokens output  (budget: 400) ← hợp lý
output_guardrail    → <5ms regex, không dùng LLM budget
final_synthesizer   → chưa đo, budget: 1000 ← cần monitor
```

### Khuyến nghị điều chỉnh

```python
# Thêm vào .env để override defaults trong settings.py:
NODE_MAX_TOKENS_INPUT_GUARDRAIL=256     # giảm từ 500 (thực tế chỉ dùng ~15 tokens)
NODE_MAX_TOKENS_SUPPORT_AGENT=256       # điều tra xem có thực sự cần 500 không
NODE_MAX_TOKENS_PLANNER_AGENT=400       # giảm từ 600 (thực tế ~25 tokens output)
NODE_MAX_TOKENS_TRAVEL_REACT_AGENT=800  # giữ: ReAct cần buffer cho tool call JSON
NODE_MAX_TOKENS_FINDING_EXTRACTOR=400   # giữ
NODE_MAX_TOKENS_FINAL_SYNTHESIZER=1024  # giữ: response dài nhất
NODE_MAX_TOKENS_CLARIFICATION_AGENT=200 # giữ
# Shadow eval (async, không ảnh hưởng hot-path latency):
NODE_MAX_TOKENS_FACT_CHECKER=600        # giảm từ 1000
NODE_MAX_TOKENS_EVALUATOR_AGENT=400     # giữ
```

> [!NOTE]
> `travel_react_agent` giữ nguyên 800 vì trong ReAct loop, model output cả JSON tool call schema + reasoning text — cần buffer đủ để không bị truncate giữa chừng (truncate tool call JSON → parse error → vòng lặp fail).

---

## Tổng Hợp — Coordinate System

```
vLLM Server               .env                concurrency.py        NodeLimits
─────────────             ───────             ──────────────        ──────────
max-num-seqs=48    ←→    MAX_COMPLETION      tier1_sem=32  ≤48     per-node ≤ 1024
                          =1024              tier2_sem=16  ≤48
max-model-len=4096 ←→    MAX_CONTEXT
                          =4096
gpu-util=0.50      ←→    (VRAM budget)       (giới hạn Python     (giới hạn từng
                          không conflict      app tự throttle)      node không ăn
                                                                     hết budget)
```

### Checklist trước khi deploy

- [ ] `gpu-util_LLM + gpu-util_Embedding ≤ 0.94` (RTX 3090 24GB)
- [ ] `max-num-seqs × KV_slot_size ≤ available VRAM cho KV cache`
- [ ] `tier1_sem + tier2_sem ≤ max-num-seqs`
- [ ] `VLLM_MAX_COMPLETION_TOKENS ≤ max-model-len`
- [ ] `mỗi NODE_MAX_TOKENS_* ≤ VLLM_MAX_COMPLETION_TOKENS`
- [ ] Sau thay đổi `concurrency.py`: **restart toàn bộ containers** (semaphore được tạo lúc import, không reload động)

---

## Các Lỗi Config Phổ Biến Cần Tránh

| Lỗi | Triệu chứng | Nguyên nhân |
|---|---|---|
| `tier1+tier2 > max-num-seqs` | Latency tăng thay vì giảm khi tăng semaphore | Python app gửi nhiều hơn server chịu được |
| `gpu-util tổng > 0.95` | OOM crash, cả 2 vLLM process bị kill | VRAM hết trong runtime |
| `NODE_MAX_TOKENS > VLLM_MAX_COMPLETION_TOKENS` | Response bị truncate, tool call JSON lỗi | Node yêu cầu nhiều hơn server cung cấp |
| `VLLM_MAX_CONTEXT_TOKENS > max-model-len` | vLLM trả 400 error "prompt too long" | Context vượt model window |
| Tăng `max-num-seqs` không restart vLLM | Không có hiệu lực | vLLM đọc tham số lúc khởi động |
| Tăng semaphore không restart containers | Semaphore cũ vẫn active | Python semaphore là object in-process |
