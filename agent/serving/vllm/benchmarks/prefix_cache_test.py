"""
Phase 2.2 — Prefix Caching Benchmark (calibrated for --max-model-len 4096)

Simulates the RAG + Multi-turn workload of the Booking Agent:
- System prompt (~1800 tokens of retrieved hotel context + instructions) is shared across turns
- Measures multiple COLD cache runs (each with a fresh session prefix nonce) vs WARM cache runs
  sharing the exact same system prompt prefix
- Scrapes delta(prefix_cache_hits) / delta(prefix_cache_queries) from vLLM /metrics

Output: serving/vllm/results/awq_prefix_cache.json
"""
import asyncio
import os
import statistics
import uuid
import httpx
from serving.vllm.benchmarks.utils import (
    PROMPTS,
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    measure_streaming_request,
    save_results,
    scrape_vllm_metrics,
)

BASE_URL = os.environ.get("VLLM_BASE_URL", DEFAULT_BASE_URL)
MODEL = os.environ.get("VLLM_MODEL", DEFAULT_MODEL)

BASE_SYSTEM_PROMPT = (
    "You are an expert travel booking assistant for BookingAI platform.\n"
    "You have access to the following retrieved hotel and flight information:\n\n"
    + PROMPTS["long"]
)

USER_QUERIES = [
    "recommend the best hotel for a family with 2 kids",
    "what is the cheapest option available?",
    "find hotels with a swimming pool under $200/night",
    "which hotel has the best reviews?",
    "what hotels are available near the beach?",
    "compare the top 3 hotels by value for money",
    "is there any hotel with airport shuttle service?",
    "what are the cancellation policies?",
    "suggest a hotel for a business trip",
    "find hotels with free breakfast included",
    "recommend a romantic hotel for a couple",
    "what is the distance from the airport?",
    "find hotels near seafood restaurants",
    "any special packages for 5-night stays?",
    "recommend the hotel with the best kids club",
    "what is the average rating of each hotel?",
    "find the hotel with the best beachfront location",
    "any hotels with infinity pool rooms?",
    "what dining amenities does each hotel offer?",
    "summarize the top recommendation in 3 bullet points",
]


async def run_prefix_cache_test():
    print(f"[Prefix Cache Test] Model: {MODEL} @ {BASE_URL}")
    print(f"Shared system prompt words: ~{len(BASE_SYSTEM_PROMPT.split())}")

    cold_ttfts = []
    warm_ttfts = []
    all_ttfts = []
    prompt_tokens_list = []

    async with httpx.AsyncClient() as client:
        # 1. Measure 3 genuine COLD runs using distinct session nonces so even repeated script runs are cold
        print("\n── Step 1: Measuring 3 COLD prefix runs (unique session prefixes) ──")
        for c_idx in range(3):
            cold_sys = f"[cold-session-{uuid.uuid4().hex}]\n" + BASE_SYSTEM_PROMPT
            m = await measure_streaming_request(
                client,
                BASE_URL,
                MODEL,
                USER_QUERIES[c_idx],
                max_tokens=64,
                system_prompt=cold_sys,
                ignore_eos=True,
            )
            cold_ttfts.append(m.ttft_ms)
            print(f"  Cold Run {c_idx + 1}: TTFT = {m.ttft_ms:.0f}ms (prompt_tokens={m.prompt_tokens})")

        # 2. Measure 1 cold + 19 warm sequential requests sharing one identical session prefix
        print("\n── Step 2: Running 20 sequential requests with shared system prompt prefix ──")
        shared_session_sys = f"[shared-rag-session-{uuid.uuid4().hex}]\n" + BASE_SYSTEM_PROMPT
        metrics_before = await scrape_vllm_metrics(BASE_URL)

        for i, query in enumerate(USER_QUERIES):
            try:
                m = await measure_streaming_request(
                    client,
                    BASE_URL,
                    MODEL,
                    query,
                    max_tokens=64,
                    system_prompt=shared_session_sys,
                    ignore_eos=True,
                )
                ttft_ms = m.ttft_ms
                if m.prompt_tokens is not None:
                    prompt_tokens_list.append(m.prompt_tokens)
                if i == 0:
                    cold_ttfts.append(ttft_ms)
                else:
                    warm_ttfts.append(ttft_ms)
            except Exception as e:
                print(f"  [WARN] Request {i + 1:02d} failed: {e}")
                ttft_ms = -1.0
            all_ttfts.append(ttft_ms)
            label = "COLD (populate)" if i == 0 else "WARM (cache hit)"
            print(f"  Request {i + 1:02d} [{label}]: TTFT = {ttft_ms:.0f}ms")

    vllm_metrics = await scrape_vllm_metrics(BASE_URL)
    if "prefix_cache_queries" in vllm_metrics and "prefix_cache_queries" in metrics_before:
        d_hits = vllm_metrics["prefix_cache_hits"] - metrics_before["prefix_cache_hits"]
        d_queries = vllm_metrics["prefix_cache_queries"] - metrics_before["prefix_cache_queries"]
        hit_rate = round(d_hits / d_queries, 4) if d_queries > 0 else 0.0
    else:
        hit_rate = vllm_metrics.get("prefix_cache_hit_rate", "N/A")

    if not cold_ttfts or not warm_ttfts:
        print("\n[ERROR] Not enough successful requests to compare cold vs warm")
        return

    avg_cold = statistics.mean(cold_ttfts)
    avg_warm = statistics.mean(warm_ttfts)
    speedup = avg_cold / avg_warm if avg_warm > 0 else 0.0
    avg_prompt_tokens = round(statistics.mean(prompt_tokens_list), 1) if prompt_tokens_list else None

    print("\n── Results ──")
    print(f"  Prompt tokens (avg, exact) : {avg_prompt_tokens}")
    print(f"  Cold TTFT avg (n={len(cold_ttfts)})      : {avg_cold:.0f}ms")
    print(f"  Warm TTFT avg (n={len(warm_ttfts)})     : {avg_warm:.0f}ms")
    print(f"  Prefill Speedup            : {speedup:.2f}x")
    print(f"  vLLM Prefix Cache Hit Rate : {hit_rate}")

    data = {
        "config": "awq_prefix_cache",
        "model": MODEL,
        "prompt_tokens_avg": avg_prompt_tokens,
        "num_requests": len(USER_QUERIES),
        "cold_ttft_avg_ms": round(avg_cold, 2),
        "warm_ttft_avg_ms": round(avg_warm, 2),
        "speedup_x": round(speedup, 2),
        "cold_ttfts_ms": [round(x, 2) for x in cold_ttfts],
        "all_ttfts_ms": [round(x, 2) for x in all_ttfts],
        "vllm_prefix_cache_hit_rate": hit_rate,
        "vllm_metrics": vllm_metrics,
    }
    save_results("awq_prefix_cache", data)


if __name__ == "__main__":
    asyncio.run(run_prefix_cache_test())
