"""
Phase 1 — Baseline Benchmark (FP16, no optimization)

Measures: TTFT, TPOT, throughput with 3 prompt lengths and multiple concurrency levels.
Output: serving/vllm/results/baseline_fp16.json

Usage:
  # 1. Start vLLM: bash serving/vllm/configs/start_baseline.sh
  # 2. Run benchmark:
  VLLM_BASE_URL=http://localhost:8000/v1 VLLM_MODEL=Qwen2.5-7B-Instruct \
    python -m serving.vllm.benchmarks.baseline_benchmark
"""
import asyncio
import os
import time
import httpx
from serving.vllm.benchmarks.utils import (
    PROMPTS, measure_streaming_request, compute_stats, save_results, scrape_vllm_metrics
)

BASE_URL = os.environ.get("VLLM_BASE_URL", "http://localhost:8000/v1")
MODEL = os.environ.get("VLLM_MODEL", "Qwen2.5-7B-Instruct")
CONCURRENCY_LEVELS = [1, 5, 10, 20]


async def run_concurrency_test(concurrency: int, prompt_key: str, num_requests: int = 20):
    """Run `concurrency` parallel requests and collect metrics."""
    prompt = PROMPTS[prompt_key]
    sem = asyncio.Semaphore(concurrency)
    results = []

    async def bounded_request(client):
        async with sem:
            return await measure_streaming_request(client, BASE_URL, MODEL, prompt)

    async with httpx.AsyncClient() as client:
        tasks = [bounded_request(client) for _ in range(num_requests)]
        start = time.perf_counter()
        raw = await asyncio.gather(*tasks, return_exceptions=True)
        total_wall_time = time.perf_counter() - start

    results = [r for r in raw if not isinstance(r, Exception)]
    errors = len(raw) - len(results)
    if errors:
        print(f"  [WARN] {errors} requests failed")

    stats = compute_stats(results)
    total_tokens = sum(r.output_tokens for r in results)
    stats["total_throughput_tps"] = total_tokens / total_wall_time if total_wall_time > 0 else 0
    stats["concurrency"] = concurrency
    stats["prompt_length"] = prompt_key
    stats["num_requests"] = num_requests
    stats["num_errors"] = errors
    return stats


async def main():
    print(f"[Baseline Benchmark] Model: {MODEL} @ {BASE_URL}")
    print("=" * 60)

    all_results = {
        "config": "baseline_fp16",
        "model": MODEL,
        "base_url": BASE_URL,
        "experiments": []
    }

    for prompt_key in ["short", "medium", "long"]:
        print(f"\n── Prompt: {prompt_key} ({len(PROMPTS[prompt_key].split())} words)")
        for concurrency in CONCURRENCY_LEVELS:
            print(f"   Concurrency={concurrency}...", end=" ", flush=True)
            stats = await run_concurrency_test(concurrency, prompt_key)
            print(f"TTFT p50={stats['ttft_p50_ms']:.0f}ms p95={stats['ttft_p95_ms']:.0f}ms | "
                  f"Throughput={stats['total_throughput_tps']:.1f} tok/s")
            all_results["experiments"].append(stats)

    # Scrape vLLM metrics for VRAM info
    vllm_metrics = await scrape_vllm_metrics(BASE_URL)
    all_results["vllm_metrics"] = vllm_metrics

    save_results("baseline_fp16", all_results)
    print("\n[Done] Baseline benchmark complete.")


if __name__ == "__main__":
    asyncio.run(main())
