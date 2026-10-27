"""
Phase 2.1 — Quantization Benchmark: FP16 vs AWQ-INT4 (Qwen/Qwen2.5-7B-Instruct-AWQ)

Measures TTFT, TPOT, system throughput, and KV cache headroom under identical
4096-context settings with salted prompts (no prefix cache bias) and fixed output length.
Output: serving/vllm/results/awq_int4.json
"""
import asyncio
import json
import os
import time
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
NUM_REQUESTS = 30
CONCURRENCY = 5


async def run_benchmark():
    prompt = PROMPTS["medium"]
    sem = asyncio.Semaphore(CONCURRENCY)

    async def bounded_req(client: httpx.AsyncClient, idx: int):
        async with sem:
            return await measure_streaming_request(
                client,
                BASE_URL,
                MODEL,
                prompt,
                max_tokens=160,
                ignore_eos=True,
                salt=True,
                req_idx=idx,
            )

    async with MetricsPoller(BASE_URL, interval_s=0.4) as poller:
        async with httpx.AsyncClient() as client:
            # 2 warmup requests
            for w in range(2):
                await measure_streaming_request(client, BASE_URL, MODEL, prompt, max_tokens=32, salt=True, req_idx=w)
            start = time.perf_counter()
            tasks = [bounded_req(client, i) for i in range(NUM_REQUESTS)]
            raw = await asyncio.gather(*tasks, return_exceptions=True)
            wall_s = time.perf_counter() - start

    results = [r for r in raw if not isinstance(r, Exception)]
    return results, wall_s, poller.summary()


async def main():
    print(f"[AWQ Benchmark] Model: {MODEL} @ {BASE_URL} (concurrency={CONCURRENCY}, n={NUM_REQUESTS})")

    results, wall_s, vllm_window = await run_benchmark()
    stats = compute_stats(results)
    total_tokens = sum(r.output_tokens for r in results)
    stats["total_throughput_tps"] = round(total_tokens / wall_s, 2) if wall_s > 0 else 0.0
    vllm_metrics = await scrape_vllm_metrics(BASE_URL)

    data = {
        "config": "awq_int4",
        "model": MODEL,
        "prompt_length": "medium",
        "num_requests": NUM_REQUESTS,
        "concurrency": CONCURRENCY,
        **stats,
        "vllm_window": vllm_window,
        "vllm_metrics": vllm_metrics,
    }

    save_results("awq_int4", data)

    baseline_path = RESULTS_DIR / "baseline_fp16.json"
    if baseline_path.exists():
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        baseline_exp = next(
            (
                e
                for e in baseline.get("experiments", [])
                if e["prompt_length"] == "medium" and e["concurrency"] == CONCURRENCY
            ),
            None,
        )
        if baseline_exp:
            print("\n── Comparison: FP16 Baseline vs AWQ-INT4 ──")
            print(f"  TTFT p50      : {baseline_exp['ttft_p50_ms']:.0f}ms -> {stats['ttft_p50_ms']:.0f}ms")
            print(f"  TPOT p50      : {baseline_exp['tpot_p50_ms']:.1f}ms -> {stats['tpot_p50_ms']:.1f}ms")
            print(f"  Sys Throughput: {baseline_exp['total_throughput_tps']:.1f} -> {stats['total_throughput_tps']:.1f} tok/s")
            b_kv = baseline_exp.get("vllm_window", {}).get("peak_kv_cache_pct")
            if b_kv is not None:
                print(f"  Peak KV Cache : {b_kv:.1f}% -> {vllm_window['peak_kv_cache_pct']:.1f}%")


if __name__ == "__main__":
    asyncio.run(main())
