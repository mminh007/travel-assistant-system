"""
Phase 2.2 — Prefix Caching Benchmark

Simulates the RAG workload of the Booking Agent:
- System prompt length ~1000 tokens (retrieved hotel context) → THIS is the cached prefix
- 20 sequential requests with the same system prompt → measures TTFT cold vs warm cache
- Scrapes cache hit rate from vLLM /metrics

Output: serving/vllm/results/awq_prefix_cache.json
"""
import asyncio
import os
import time
import httpx
import json
from serving.vllm.benchmarks.utils import (
    PROMPTS, measure_streaming_request, save_results, scrape_vllm_metrics
)

BASE_URL = os.environ.get("VLLM_BASE_URL", "http://localhost:8000/v1")
MODEL = os.environ.get("VLLM_MODEL", "Qwen2.5-7B-Instruct-AWQ")

# Simulates the exact RAG system prompt pattern in the Booking Agent's final_synthesizer
SYSTEM_PROMPT_PREFIX = (
    "You are an expert travel booking assistant for BookingAI platform.\n"
    "You have access to the following retrieved hotel and flight information:\n\n"
    + PROMPTS["long"]  # ~1800 tokens — same system prompt repeated = prefix cache should hit
    + "\n\nBased on the above context, "
)

USER_QUERIES = [
    "recommend the best hotel for a family with 2 kids",
    "what is the cheapest option available?",
    "find hotels with a swimming pool under $200/night",
    "which hotel has the best reviews?",
    "what hotels are available near the city center?",
    "compare the top 3 hotels by value for money",
    "is there any hotel that allows pets?",
    "find a hotel with airport shuttle service",
    "what are the cancellation policies?",
    "suggest a hotel for a business trip",
    "find hotels with free breakfast included",
    "recommend a romantic hotel for a couple",
    "what is the check-in time for each hotel?",
    "find hotels near public transport",
    "any special discounts for long stays?",
    "recommend the hotel with the best gym facilities",
    "what is the average rating of each hotel?",
    "find the hotel with the best location",
    "any hotels with sea view rooms?",
    "what amenities does each hotel offer?",
]


async def run_prefix_cache_test():
    print(f"[Prefix Cache Test] Model: {MODEL}")
    print(f"System prompt length: ~{len(SYSTEM_PROMPT_PREFIX.split())} words")
    print("Running 20 sequential requests with identical system prompt prefix...\n")

    # Snapshot counters before the test so the hit rate reflects ONLY this test
    metrics_before = await scrape_vllm_metrics(BASE_URL)

    ttft_results = []
    prompt_tokens_list = []
    async with httpx.AsyncClient() as client:
        for i, query in enumerate(USER_QUERIES):
            full_prompt = SYSTEM_PROMPT_PREFIX + query
            try:
                m = await measure_streaming_request(
                    client, BASE_URL, MODEL, full_prompt, max_tokens=100
                )
                ttft_ms = m.ttft_ms
                if m.prompt_tokens is not None:
                    prompt_tokens_list.append(m.prompt_tokens)
            except Exception as e:
                print(f"  [WARN] Request {i+1:02d} failed: {e}")
                ttft_ms = -1
            ttft_results.append(ttft_ms)
            label = "COLD" if i == 0 else "WARM"
            print(f"  Request {i+1:02d} [{label}]: TTFT = {ttft_ms:.0f}ms")

    # Prefix cache hit rate for this test = delta(hits) / delta(queries)
    vllm_metrics = await scrape_vllm_metrics(BASE_URL)
    if "prefix_cache_queries" in vllm_metrics and "prefix_cache_queries" in metrics_before:
        d_hits = vllm_metrics["prefix_cache_hits"] - metrics_before["prefix_cache_hits"]
        d_queries = vllm_metrics["prefix_cache_queries"] - metrics_before["prefix_cache_queries"]
        hit_rate = d_hits / d_queries if d_queries > 0 else 0.0
    else:
        # Legacy V0 gauge (cumulative since server start)
        hit_rate = vllm_metrics.get("prefix_cache_hit_rate", "N/A")

    valid = [t for t in ttft_results if t >= 0]
    if len(valid) < 2 or ttft_results[0] < 0:
        print("\n[ERROR] Not enough successful requests to compare cold vs warm")
        return
    cold_ttft = ttft_results[0]
    warm_ttfts = [t for t in ttft_results[1:] if t >= 0]
    avg_warm = sum(warm_ttfts) / len(warm_ttfts) if warm_ttfts else 0
    speedup = cold_ttft / avg_warm if avg_warm > 0 else 0
    avg_prompt_tokens = (
        sum(prompt_tokens_list) / len(prompt_tokens_list) if prompt_tokens_list else None
    )

    print(f"\n── Results ──")
    print(f"  Prompt tokens (avg, exact): {avg_prompt_tokens}")
    print(f"  Cold TTFT (req 1):  {cold_ttft:.0f}ms")
    print(f"  Warm TTFT (avg req 2-20): {avg_warm:.0f}ms")
    print(f"  Speedup: {speedup:.1f}x")
    print(f"  vLLM Prefix Cache Hit Rate (this test): {hit_rate}")

    data = {
        "config": "awq_prefix_cache",
        "model": MODEL,
        "system_prompt_tokens_approx": len(SYSTEM_PROMPT_PREFIX.split()),
        "prompt_tokens_avg": avg_prompt_tokens,
        "num_requests": len(USER_QUERIES),
        "cold_ttft_ms": cold_ttft,
        "warm_ttft_avg_ms": avg_warm,
        "speedup_x": speedup,
        "all_ttfts_ms": ttft_results,
        "vllm_prefix_cache_hit_rate": hit_rate,
        "vllm_metrics": vllm_metrics,
    }
    save_results("awq_prefix_cache", data)


if __name__ == "__main__":
    asyncio.run(run_prefix_cache_test())
