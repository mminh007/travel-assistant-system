"""
Phase 2.3 — Chunked Prefill Test

Compares TTFT distribution with long prompts (2000+ tokens):
  - Without chunked prefill: High TTFT spike (entire prefill block decode)
  - With chunked prefill:    Reduced TTFT spike (prefill divided into chunks)

Output: serving/vllm/results/chunked_prefill.json
"""
import asyncio
import os
import statistics
import httpx
import json
import time
from serving.vllm.benchmarks.utils import (
    PROMPTS, measure_streaming_request, compute_stats, save_results
)

BASE_URL = os.environ.get("VLLM_BASE_URL", "http://localhost:8000/v1")
MODEL = os.environ.get("VLLM_MODEL", "Qwen2.5-7B-Instruct-AWQ")
CONFIG_NAME = os.environ.get("BENCHMARK_CONFIG", "awq_chunked_prefill")
NUM_REQUESTS = 20


async def main():
    print(f"[Chunked Prefill Test] Config: {CONFIG_NAME}")
    prompt = PROMPTS["long"]  # 1800+ tokens

    async with httpx.AsyncClient() as client:
        tasks = [
            measure_streaming_request(client, BASE_URL, MODEL, prompt, max_tokens=150)
            for _ in range(NUM_REQUESTS)
        ]
        raw = await asyncio.gather(*tasks, return_exceptions=True)

    results = [r for r in raw if not isinstance(r, Exception)]
    stats = compute_stats(results)
    ttfts = sorted(r.ttft_ms for r in results)

    print(f"  TTFT p50={stats['ttft_p50_ms']:.0f}ms "
          f"p95={stats['ttft_p95_ms']:.0f}ms "
          f"p99={stats['ttft_p99_ms']:.0f}ms")

    data = {
        "config": CONFIG_NAME,
        "model": MODEL,
        "prompt_length": "long (~1800 tokens)",
        "num_requests": NUM_REQUESTS,
        **stats,
        "all_ttfts_ms": ttfts,
    }
    save_results(CONFIG_NAME, data)


if __name__ == "__main__":
    asyncio.run(main())
