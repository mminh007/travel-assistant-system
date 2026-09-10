"""
Phase 2.1 — Quantization Benchmark: FP16 vs AWQ-INT4

Compares 2 configs by reading the existing baseline results and running an AWQ run.
Output: serving/vllm/results/awq_int4.json

Usage (vLLM must be running with AWQ config):
  bash serving/vllm/configs/start_awq.sh
  VLLM_BASE_URL=... VLLM_MODEL=Qwen2.5-7B-Instruct-AWQ \
    python -m serving.vllm.benchmarks.quant_benchmark
"""
import asyncio
import json
import os
from pathlib import Path
from serving.vllm.benchmarks.utils import (
    PROMPTS, measure_streaming_request, compute_stats, save_results,
    scrape_vllm_metrics, RESULTS_DIR
)

BASE_URL = os.environ.get("VLLM_BASE_URL", "http://localhost:8000/v1")
MODEL = os.environ.get("VLLM_MODEL", "Qwen2.5-7B-Instruct-AWQ")
NUM_REQUESTS = 30
CONCURRENCY = 5


async def run_benchmark():
    import httpx
    prompt = PROMPTS["medium"]
    sem = asyncio.Semaphore(CONCURRENCY)

    async def bounded_req(client):
        async with sem:
            return await measure_streaming_request(client, BASE_URL, MODEL, prompt)

    async with httpx.AsyncClient() as client:
        tasks = [bounded_req(client) for _ in range(NUM_REQUESTS)]
        raw = await asyncio.gather(*tasks, return_exceptions=True)

    results = [r for r in raw if not isinstance(r, Exception)]
    return results


async def main():
    print(f"[AWQ Benchmark] Model: {MODEL} @ {BASE_URL}")

    results = await run_benchmark()
    stats = compute_stats(results)
    vllm_metrics = await scrape_vllm_metrics(BASE_URL)

    data = {
        "config": "awq_int4",
        "model": MODEL,
        "num_requests": NUM_REQUESTS,
        "concurrency": CONCURRENCY,
        **stats,
        "vllm_metrics": vllm_metrics,
    }

    save_results("awq_int4", data)

    # Load baseline for comparison
    baseline_path = RESULTS_DIR / "baseline_fp16.json"
    if baseline_path.exists():
        baseline = json.loads(baseline_path.read_text())
        # Find comparable experiment (medium prompt, concurrency=5)
        baseline_exp = next(
            (e for e in baseline.get("experiments", [])
             if e["prompt_length"] == "medium" and e["concurrency"] == CONCURRENCY),
            None
        )
        if baseline_exp:
            print("\n── Comparison: FP16 Baseline vs AWQ-INT4 ──")
            print(f"  TTFT p50: {baseline_exp['ttft_p50_ms']:.0f}ms → {stats['ttft_p50_ms']:.0f}ms")
            print(f"  TTFT p95: {baseline_exp['ttft_p95_ms']:.0f}ms → {stats['ttft_p95_ms']:.0f}ms")
            print(f"  Throughput: {baseline_exp['avg_throughput_tps']:.1f} → {stats['avg_throughput_tps']:.1f} tok/s")


if __name__ == "__main__":
    asyncio.run(main())
