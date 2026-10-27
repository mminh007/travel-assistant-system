"""
Phase 1 — Baseline Benchmark (FP16 or AWQ without prefix-cache cheating)

Measures: TTFT, TPOT, max ITL, throughput, peak KV cache %, waiting queue depth, and preemptions
across 3 prompt lengths (calibrated for --max-model-len 4096) and multiple concurrency levels.
Each request uses a unique nonce salt so prefix caching does not skew baseline TTFT.

Output: serving/vllm/results/baseline_fp16.json
"""
import asyncio
import os
import time
import httpx
from serving.vllm.benchmarks.utils import (
    PROMPTS,
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    MetricsPoller,
    measure_streaming_request,
    compute_stats,
    save_results,
    scrape_vllm_metrics,
)

BASE_URL = os.environ.get("VLLM_BASE_URL", DEFAULT_BASE_URL)
MODEL = os.environ.get("VLLM_MODEL", DEFAULT_MODEL)
CONFIG_NAME = os.environ.get("BENCHMARK_CONFIG", "baseline_fp16")
CONCURRENCY_LEVELS = [1, 5, 10, 20]


async def warmup(base_url: str, model: str):
    async with httpx.AsyncClient() as client:
        for _ in range(2):
            try:
                await measure_streaming_request(
                    client, base_url, model, PROMPTS["short"], max_tokens=32, salt=True
                )
            except Exception as e:
                print(f"  [WARN] Warmup request failed: {e}")


async def run_concurrency_test(concurrency: int, prompt_key: str, num_requests: int = 0) -> dict:
    """Run `concurrency` parallel requests with unique salted prompts and collect metrics."""
    if num_requests <= 0:
        num_requests = max(20, concurrency * 3)
    prompt = PROMPTS[prompt_key]
    sem = asyncio.Semaphore(concurrency)

    async def bounded_request(client: httpx.AsyncClient, idx: int):
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

    limits = httpx.Limits(max_connections=concurrency + 10, max_keepalive_connections=concurrency + 5)
    async with MetricsPoller(BASE_URL, interval_s=0.4) as poller:
        async with httpx.AsyncClient(limits=limits) as client:
            tasks = [bounded_request(client, i) for i in range(num_requests)]
            start = time.perf_counter()
            raw = await asyncio.gather(*tasks, return_exceptions=True)
            total_wall_time = time.perf_counter() - start

    results = [r for r in raw if not isinstance(r, Exception)]
    errors = len(raw) - len(results)
    if errors:
        print(f"  [WARN] {errors}/{num_requests} requests failed")

    stats = compute_stats(results)
    vllm_window = poller.summary()
    total_tokens = sum(r.output_tokens for r in results)
    stats["total_throughput_tps"] = round(total_tokens / total_wall_time, 2) if total_wall_time > 0 else 0.0
    stats["concurrency"] = concurrency
    stats["prompt_length"] = prompt_key
    stats["num_requests"] = num_requests
    stats["num_errors"] = errors
    stats["vllm_window"] = vllm_window
    return stats


async def main():
    print(f"[Baseline Benchmark] Config: {CONFIG_NAME} | Model: {MODEL} @ {BASE_URL}")
    print("=" * 72)
    await warmup(BASE_URL, MODEL)

    all_results = {
        "config": CONFIG_NAME,
        "model": MODEL,
        "base_url": BASE_URL,
        "experiments": [],
    }

    for prompt_key in ["short", "medium", "long"]:
        print(f"\n── Prompt: {prompt_key} (~{len(PROMPTS[prompt_key].split())} words)")
        for concurrency in CONCURRENCY_LEVELS:
            print(f"   Concurrency={concurrency:2d}...", end=" ", flush=True)
            stats = await run_concurrency_test(concurrency, prompt_key)
            vw = stats["vllm_window"]
            print(
                f"TTFT p50={stats['ttft_p50_ms']:.0f}ms p95={stats['ttft_p95_ms']:.0f}ms | "
                f"TPOT p50={stats['tpot_p50_ms']:.1f}ms | "
                f"SysTok/s={stats['total_throughput_tps']:.1f} | "
                f"PeakKV={vw['peak_kv_cache_pct']:.1f}% Queue={vw['peak_waiting_requests']} Preempt={vw['preemptions_delta']}"
            )
            all_results["experiments"].append(stats)

    all_results["vllm_metrics"] = await scrape_vllm_metrics(BASE_URL)
    save_results(CONFIG_NAME, all_results)
    print("\n[Done] Baseline benchmark complete.")


if __name__ == "__main__":
    asyncio.run(main())
