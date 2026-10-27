"""
Phase 2.3 — Chunked Prefill Benchmark (Mixed Short-Decode + Long-Prefill Interference Test)

Why a mixed workload is required:
  Chunked prefill splits long prompt prefills (~1800 tokens) into smaller chunks (e.g. 512 tokens)
  so ongoing decode streams do NOT stall for ratusan ms when a long RAG prompt arrives.

Workload:
  - 4 continuous short-prompt decode streams (measuring TPOT & max Inter-Token Latency stall)
  - 8 concurrent long-prompt RAG bursts (~1800 tokens, salted) injected while decodes are in-flight

Output: serving/vllm/results/<BENCHMARK_CONFIG>.json (default: awq_chunked_prefill)
"""
import asyncio
import os
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
CONFIG_NAME = os.environ.get("BENCHMARK_CONFIG", "awq_chunked_prefill")
NUM_DECODE_STREAMS = 8
NUM_LONG_PREFILLS = 12


async def main():
    print(f"[Chunked Prefill Mixed Test] Config: {CONFIG_NAME} | Model: {MODEL} @ {BASE_URL}")

    sem = asyncio.Semaphore(8)

    async def decode_stream(client: httpx.AsyncClient, idx: int):
        async with sem:
            return await measure_streaming_request(
                client,
                BASE_URL,
                MODEL,
                PROMPTS["short"],
                max_tokens=220,
                ignore_eos=True,
                salt=True,
                req_idx=idx,
            )

    async def long_prefill_request(client: httpx.AsyncClient, idx: int):
        # Slight stagger so long prefills collide with active decode streams
        await asyncio.sleep(0.15 * (idx % 4))
        async with sem:
            return await measure_streaming_request(
                client,
                BASE_URL,
                MODEL,
                PROMPTS["long"],
                max_tokens=80,
                ignore_eos=True,
                salt=True,
                req_idx=100 + idx,
            )

    async with MetricsPoller(BASE_URL, interval_s=0.3) as poller:
        async with httpx.AsyncClient() as client:
            decode_tasks = [decode_stream(client, i) for i in range(NUM_DECODE_STREAMS)]
            long_tasks = [long_prefill_request(client, i) for i in range(NUM_LONG_PREFILLS)]
            raw_decode, raw_long = await asyncio.gather(
                asyncio.gather(*decode_tasks, return_exceptions=True),
                asyncio.gather(*long_tasks, return_exceptions=True),
            )

    decode_results = [r for r in raw_decode if not isinstance(r, Exception)]
    long_results = [r for r in raw_long if not isinstance(r, Exception)]

    decode_stats = compute_stats(decode_results)
    long_stats = compute_stats(long_results)
    vllm_window = poller.summary()

    print(
        f"  Decode Streams : TPOT p50={decode_stats['tpot_p50_ms']:.1f}ms p95={decode_stats['tpot_p95_ms']:.1f}ms | "
        f"Max ITL Stall p95={decode_stats['itl_max_p95_ms']:.0f}ms"
    )
    print(
        f"  Long Prefills  : TTFT p50={long_stats['ttft_p50_ms']:.0f}ms p95={long_stats['ttft_p95_ms']:.0f}ms "
        f"p99={long_stats['ttft_p99_ms']:.0f}ms"
    )

    data = {
        "config": CONFIG_NAME,
        "model": MODEL,
        "decode_stream_stats": decode_stats,
        "long_prefill_stats": long_stats,
        "vllm_window": vllm_window,
        "vllm_metrics": await scrape_vllm_metrics(BASE_URL),
    }
    save_results(CONFIG_NAME, data)


if __name__ == "__main__":
    asyncio.run(main())
