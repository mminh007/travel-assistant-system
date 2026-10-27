"""
Phase 2.5 — Speculative Decoding Benchmark

Measures:
  - Draft token acceptance rate (scraped from vLLM /metrics delta counters)
  - TPOT & decode throughput speedup vs AWQ baseline (Spec decoding accelerates DECODE, not TTFT)
  - Concurrency strictly bounded by semaphore (default CONCURRENCY=1)

Output: serving/vllm/results/awq_spec_decoding_k<SPEC_TOKENS>.json
"""
import asyncio
import json
import os
import httpx
from serving.vllm.benchmarks.utils import (
    PROMPTS,
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    RESULTS_DIR,
    MetricsPoller,
    measure_streaming_request,
    compute_stats,
    save_results,
    scrape_vllm_metrics,
)

BASE_URL = os.environ.get("VLLM_BASE_URL", DEFAULT_BASE_URL)
MODEL = os.environ.get("VLLM_MODEL", DEFAULT_MODEL)
SPEC_TOKENS = int(os.environ.get("SPEC_TOKENS", "5"))
NUM_REQUESTS = 20
CONCURRENCY = int(os.environ.get("SPEC_CONCURRENCY", "1"))


async def main():
    print(
        f"[Spec Decoding Test] Model: {MODEL} | k={SPEC_TOKENS} | "
        f"concurrency={CONCURRENCY} | requests={NUM_REQUESTS}"
    )

    sem = asyncio.Semaphore(CONCURRENCY)

    async def bounded_req(client: httpx.AsyncClient, idx: int):
        async with sem:
            return await measure_streaming_request(
                client,
                BASE_URL,
                MODEL,
                PROMPTS["medium"],
                max_tokens=200,
                ignore_eos=True,
                salt=True,
                req_idx=idx,
            )

    async with MetricsPoller(BASE_URL, interval_s=0.4) as poller:
        async with httpx.AsyncClient() as client:
            tasks = [bounded_req(client, i) for i in range(NUM_REQUESTS)]
            raw = await asyncio.gather(*tasks, return_exceptions=True)

    results = [r for r in raw if not isinstance(r, Exception)]
    stats = compute_stats(results)
    vllm_window = poller.summary()
    vllm_metrics = await scrape_vllm_metrics(BASE_URL)
    acceptance_rate = vllm_window.get("spec_acceptance_rate_delta") or vllm_metrics.get("spec_acceptance_rate")

    # Compare decode TPOT & throughput against awq_int4 or baseline_fp16
    tpot_speedup = None
    ref_path = RESULTS_DIR / "awq_int4.json"
    if ref_path.exists():
        ref = json.loads(ref_path.read_text(encoding="utf-8"))
        if ref.get("tpot_p50_ms", 0) > 0 and stats.get("tpot_p50_ms", 0) > 0:
            tpot_speedup = round(ref["tpot_p50_ms"] / stats["tpot_p50_ms"], 2)

    print(
        f"  TPOT p50={stats['tpot_p50_ms']:.1f}ms p95={stats['tpot_p95_ms']:.1f}ms | "
        f"Decode tok/s={stats['avg_decode_tps']:.1f} | "
        f"Draft Acceptance Rate={acceptance_rate}"
    )
    if tpot_speedup:
        print(f"  Decode Speedup vs AWQ: {tpot_speedup:.2f}x")

    data = {
        "config": f"awq_spec_decoding_k{SPEC_TOKENS}",
        "model": MODEL,
        "num_speculative_tokens": SPEC_TOKENS,
        "concurrency": CONCURRENCY,
        "num_requests": NUM_REQUESTS,
        **stats,
        "draft_acceptance_rate": acceptance_rate,
        "decode_speedup_vs_awq": tpot_speedup,
        "vllm_window": vllm_window,
        "vllm_metrics": vllm_metrics,
    }
    save_results(f"awq_spec_decoding_k{SPEC_TOKENS}", data)


if __name__ == "__main__":
    asyncio.run(main())
