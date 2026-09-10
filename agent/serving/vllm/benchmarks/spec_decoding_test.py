"""
Phase 2.5 — Speculative Decoding Benchmark

Measures:
  - Acceptance rate: % of draft tokens accepted by the main model
  - Speedup: compared to baseline without spec decoding
  - Sweet spot: num_speculative_tokens = 3, 5, 7

Output: serving/vllm/results/awq_spec_decoding.json

Usage:
  # Test num_spec_tokens=5 (default):
  bash serving/vllm/configs/start_spec_decoding.sh
  SPEC_TOKENS=5 VLLM_BASE_URL=... python -m serving.vllm.benchmarks.spec_decoding_test
"""
import asyncio
import os
import json
import time
import httpx
from serving.vllm.benchmarks.utils import (
    PROMPTS, measure_streaming_request, compute_stats, save_results,
    scrape_vllm_metrics, RESULTS_DIR
)

BASE_URL = os.environ.get("VLLM_BASE_URL", "http://localhost:8000/v1")
MODEL = os.environ.get("VLLM_MODEL", "Qwen2.5-7B-Instruct-AWQ")
SPEC_TOKENS = int(os.environ.get("SPEC_TOKENS", "5"))
NUM_REQUESTS = 30
CONCURRENCY = 1   # Spec decoding works best with single requests


async def main():
    print(f"[Spec Decoding Test] Model: {MODEL}, num_speculative_tokens={SPEC_TOKENS}")

    async with httpx.AsyncClient() as client:
        tasks = [
            measure_streaming_request(client, BASE_URL, MODEL, PROMPTS["medium"])
            for _ in range(NUM_REQUESTS)
        ]
        raw = await asyncio.gather(*tasks, return_exceptions=True)

    results = [r for r in raw if not isinstance(r, Exception)]
    stats = compute_stats(results)
    vllm_metrics = await scrape_vllm_metrics(BASE_URL)

    # Load baseline for speedup calculation
    speedup = None
    baseline_path = RESULTS_DIR / "baseline_fp16.json"
    if baseline_path.exists():
        baseline = json.loads(baseline_path.read_text())
        baseline_exp = next(
            (e for e in baseline.get("experiments", [])
             if e["prompt_length"] == "medium" and e["concurrency"] == 1),
            None
        )
        if baseline_exp:
            speedup = baseline_exp["ttft_p50_ms"] / stats["ttft_p50_ms"]
            print(f"  Speedup vs baseline: {speedup:.2f}x")

    print(f"  TTFT p50={stats['ttft_p50_ms']:.0f}ms p95={stats['ttft_p95_ms']:.0f}ms")

    data = {
        "config": f"awq_spec_decoding_k{SPEC_TOKENS}",
        "model": MODEL,
        "num_speculative_tokens": SPEC_TOKENS,
        "num_requests": NUM_REQUESTS,
        **stats,
        "speedup_vs_baseline": speedup,
        "vllm_metrics": vllm_metrics,
    }
    save_results(f"awq_spec_decoding_k{SPEC_TOKENS}", data)


if __name__ == "__main__":
    asyncio.run(main())
