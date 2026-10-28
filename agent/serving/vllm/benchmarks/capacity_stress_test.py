"""
Phase 3 — System Capacity, KV Cache Saturation & Co-located Embedding Stress Test

Designed for the vast.ai deployment running BOTH models on a single GPU (--max-model-len 4096):
  1. LLM:       Qwen/Qwen2.5-3B-Instruct-AWQ (port 8080, gpu-memory-utilization=0.50)
  2. Embedding: Qwen/Qwen3-Embedding-4B      (port 8081, gpu-memory-utilization=0.38)

What this benchmark measures:
  - Step-up concurrency ramp (1 -> 4 -> 8 -> 16 -> 24 -> 32 concurrent users)
  - Simultaneous RAG Embedding traffic against port 8081 while LLM is under load
  - Exact Knee Point where waiting queue > 0 or KV cache preemptions > 0
  - Goodput (tok/s and req/s meeting SLO: TTFT <= 1500ms & TPOT <= 60ms)
  - Recommended tuning for `agent/app/core/concurrency.py` (TIER1_SEMAPHORE / TIER2_SEMAPHORE)

Output: serving/vllm/results/capacity_stress_test.json
"""
import asyncio
import os
import statistics
import time
import httpx
from serving.vllm.benchmarks.utils import (
    PROMPTS,
    DEFAULT_BASE_URL,
    DEFAULT_EMBEDDING_BASE_URL,
    DEFAULT_MODEL,
    DEFAULT_EMBEDDING_MODEL,
    MetricsPoller,
    percentile_linear,
    measure_streaming_request,
    compute_stats,
    save_results,
    scrape_vllm_metrics,
)

BASE_URL = os.environ.get("VLLM_BASE_URL", DEFAULT_BASE_URL)
EMBED_BASE_URL = os.environ.get("VLLM_EMBEDDING_BASE_URL", DEFAULT_EMBEDDING_BASE_URL)
MODEL = os.environ.get("VLLM_MODEL", DEFAULT_MODEL)
EMBED_MODEL = os.environ.get("VLLM_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL)

CONCURRENCY_STEPS = [1, 4, 8, 12, 16, 24, 32]
SLO_TTFT_MS = float(os.environ.get("SLO_TTFT_MS", "1500"))
SLO_TPOT_MS = float(os.environ.get("SLO_TPOT_MS", "60"))

RAG_EMBED_QUERIES = [
    "khách sạn 5 sao gần biển Mỹ Khê Đà Nẵng có hồ bơi vô cực",
    "family friendly resort in Nha Trang with kids club under 3 million VND",
    "boutique hotel in Old Quarter Hanoi with airport shuttle and free breakfast",
    "romantic beachfront villa in Phu Quoc for honeymoon couple",
    "business hotel in District 1 Ho Chi Minh City near conference center",
]


async def measure_embedding_request(client: httpx.AsyncClient, text: str) -> float:
    start = time.perf_counter()
    resp = await client.post(
        f"{EMBED_BASE_URL.rstrip('/')}/embeddings",
        json={"model": EMBED_MODEL, "input": text},
        timeout=30.0,
    )
    resp.raise_for_status()
    return (time.perf_counter() - start) * 1000.0


async def run_step(concurrency: int) -> dict:
    num_llm_reqs = max(16, concurrency * 2)
    num_embed_reqs = max(8, concurrency)
    llm_sem = asyncio.Semaphore(concurrency)
    embed_sem = asyncio.Semaphore(max(2, concurrency // 2))

    # Mix 50% medium + 50% long prompts (~1800 tokens) to stress KV cache realistically
    async def llm_worker(client: httpx.AsyncClient, idx: int):
        prompt_key = "long" if idx % 2 == 0 else "medium"
        async with llm_sem:
            return await measure_streaming_request(
                client,
                BASE_URL,
                MODEL,
                PROMPTS[prompt_key],
                max_tokens=160,
                ignore_eos=True,
                salt=True,
                req_idx=idx,
            )

    async def embed_worker(client: httpx.AsyncClient, idx: int):
        q = RAG_EMBED_QUERIES[idx % len(RAG_EMBED_QUERIES)]
        async with embed_sem:
            return await measure_embedding_request(client, f"[q-{idx}] {q}")

    limits = httpx.Limits(max_connections=concurrency * 2 + 10, max_keepalive_connections=concurrency + 10)
    async with MetricsPoller(BASE_URL, interval_s=0.35) as poller:
        async with httpx.AsyncClient(limits=limits) as client:
            start = time.perf_counter()
            llm_tasks = [llm_worker(client, i) for i in range(num_llm_reqs)]
            embed_tasks = [embed_worker(client, i) for i in range(num_embed_reqs)]
            raw_llm, raw_embed = await asyncio.gather(
                asyncio.gather(*llm_tasks, return_exceptions=True),
                asyncio.gather(*embed_tasks, return_exceptions=True),
            )
            wall_s = time.perf_counter() - start

    llm_ok = [r for r in raw_llm if not isinstance(r, Exception)]
    embed_ok = sorted(r for r in raw_embed if not isinstance(r, Exception))

    stats = compute_stats(llm_ok, slo_ttft_ms=SLO_TTFT_MS, slo_tpot_ms=SLO_TPOT_MS)
    vw = poller.summary()
    total_tokens = sum(r.output_tokens for r in llm_ok)
    sys_tps = round(total_tokens / wall_s, 2) if wall_s > 0 else 0.0
    goodput_tps = round(sys_tps * (stats["slo_attainment_pct"] / 100.0), 2)

    embed_stats = {
        "embed_requests": num_embed_reqs,
        "embed_errors": num_embed_reqs - len(embed_ok),
        "embed_p50_ms": round(percentile_linear(embed_ok, 50), 2) if embed_ok else None,
        "embed_p95_ms": round(percentile_linear(embed_ok, 95), 2) if embed_ok else None,
    }

    return {
        "concurrency": concurrency,
        "num_llm_requests": num_llm_reqs,
        "num_llm_errors": num_llm_reqs - len(llm_ok),
        **stats,
        "total_throughput_tps": sys_tps,
        "goodput_tps": goodput_tps,
        "embedding_co_load": embed_stats,
        "vllm_window": vw,
    }


async def main():
    print(f"[Capacity & KV Preemption Stress Test]")
    print(f"  LLM      : {MODEL} @ {BASE_URL}")
    print(f"  Embedding: {EMBED_MODEL} @ {EMBED_BASE_URL}")
    print(f"  SLOs     : TTFT <= {SLO_TTFT_MS:.0f}ms | TPOT <= {SLO_TPOT_MS:.0f}ms")
    print("=" * 80)

    steps = []
    knee_concurrency = CONCURRENCY_STEPS[0]

    for c in CONCURRENCY_STEPS:
        print(f"  Step Concurrency={c:2d} ...", end=" ", flush=True)
        step_res = await run_step(c)
        vw = step_res["vllm_window"]
        em = step_res["embedding_co_load"]
        print(
            f"TTFT p95={step_res['ttft_p95_ms']:5.0f}ms | "
            f"TPOT p95={step_res['tpot_p95_ms']:4.1f}ms | "
            f"Tok/s={step_res['total_throughput_tps']:5.1f} (Goodput={step_res['goodput_tps']:5.1f}) | "
            f"KV={vw['peak_kv_cache_pct']:4.1f}% Wait={vw['peak_waiting_requests']:2d} Preempt={vw['preemptions_delta']} | "
            f"Embed p95={em['embed_p95_ms'] or 0:.0f}ms"
        )
        steps.append(step_res)
        if step_res["slo_attainment_pct"] >= 90.0 and vw["preemptions_delta"] == 0:
            knee_concurrency = c

    rec_tier2 = max(2, knee_concurrency // 2)
    rec_tier1 = max(4, knee_concurrency)
    print("\n── Capacity Summary & Agent Tuning Recommendation ──")
    print(f"  Max Healthy Concurrency (SLO >= 90%, 0 preemptions): {knee_concurrency}")
    print(f"  Recommended app/core/concurrency.py settings for vLLM: tier1={rec_tier1}, tier2={rec_tier2}")

    save_results(
        "capacity_stress_test",
        {
            "config": "capacity_stress_test",
            "model": MODEL,
            "embedding_model": EMBED_MODEL,
            "slo_ttft_ms": SLO_TTFT_MS,
            "slo_tpot_ms": SLO_TPOT_MS,
            "knee_concurrency": knee_concurrency,
            "recommended_agent_concurrency": {"tier1": rec_tier1, "tier2": rec_tier2},
            "steps": steps,
            "vllm_metrics_final": await scrape_vllm_metrics(BASE_URL),
        },
    )


if __name__ == "__main__":
    asyncio.run(main())
