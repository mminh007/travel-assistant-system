"""
Shared utilities for all benchmark scripts.
- TTFT measurement via streaming
- Percentile calculations (p50, p95, p99)
- JSON results saving
- vLLM metrics scraping (VRAM, KV cache hit rate...)
"""
import asyncio
import json
import time
import statistics
import httpx
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, asdict

RESULTS_DIR = Path(__file__).parent.parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)


@dataclass
class RequestMetrics:
    ttft_ms: float          # Time To First Token (ms)
    tpot_ms: float          # Time Per Output Token (ms)
    total_latency_ms: float # End-to-end latency (ms)
    output_tokens: int      # Number of tokens generated
    throughput_tps: float   # tokens/second
    prompt_tokens: Optional[int] = None  # Input tokens (from server usage)
    token_count_source: str = "usage"    # "usage" (exact) | "sse_chunks" (fallback, approximate)


@dataclass
class BenchmarkResult:
    config_name: str
    model: str
    prompt_length: str        # "short" | "medium" | "long"
    concurrency: int
    num_requests: int
    
    # Latency stats
    ttft_p50_ms: float
    ttft_p95_ms: float
    ttft_p99_ms: float
    tpot_p50_ms: float
    tpot_p95_ms: float
    
    # Throughput
    avg_throughput_tps: float
    total_throughput_tps: float   # system-level
    
    # Optional — scraped from vLLM /metrics
    vram_used_gb: Optional[float] = None
    kv_cache_usage_pct: Optional[float] = None
    prefix_cache_hit_rate: Optional[float] = None


async def measure_streaming_request(
    client: httpx.AsyncClient,
    base_url: str,
    model: str,
    prompt: str,
    max_tokens: int = 200,
) -> RequestMetrics:
    """
    Sends 1 request to vLLM and measures TTFT, TPOT, throughput.
    Uses SSE streaming to measure exact TTFT (ms when first token arrives).

    Token counts come from the server-reported `usage` (enabled via
    stream_options.include_usage). Counting SSE chunks is only a fallback:
    one chunk may carry several tokens (e.g. speculative decoding) or none.
    """
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "stream": True,
        "stream_options": {"include_usage": True},
        "temperature": 0.0,
    }

    start_time = time.perf_counter()
    first_token_time = None
    last_token_time = None
    chunk_count = 0          # fallback only — approximate
    prompt_tokens = None
    completion_tokens = None

    async with client.stream(
        "POST",
        f"{base_url}/chat/completions",
        json=payload,
        timeout=120.0,
    ) as response:
        response.raise_for_status()
        async for line in response.aiter_lines():
            if not line.startswith("data: "):
                continue
            data_str = line[6:]
            if data_str.strip() == "[DONE]":
                break
            try:
                data = json.loads(data_str)
            except json.JSONDecodeError:
                continue

            # Final usage chunk has `usage` set and an empty `choices` list
            usage = data.get("usage")
            if usage:
                prompt_tokens = usage.get("prompt_tokens")
                completion_tokens = usage.get("completion_tokens")

            choices = data.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta", {}).get("content", "")
            if delta:
                now = time.perf_counter()
                if first_token_time is None:
                    first_token_time = now
                last_token_time = now
                chunk_count += 1

    end_time = time.perf_counter()

    if first_token_time is None:
        raise ValueError("No tokens received from vLLM")

    if completion_tokens is not None:
        output_tokens = completion_tokens
        source = "usage"
    else:
        output_tokens = chunk_count
        source = "sse_chunks"
        print("[WARN] Server did not return usage; token count is approximate (SSE chunks)")

    ttft_ms = (first_token_time - start_time) * 1000
    total_ms = (end_time - start_time) * 1000

    # TPOT = decode time / number of tokens after the first
    # (same definition as `vllm bench serve`)
    if output_tokens > 1:
        tpot_ms = (last_token_time - first_token_time) * 1000 / (output_tokens - 1)
    else:
        tpot_ms = 0.0

    throughput_tps = output_tokens / (total_ms / 1000) if total_ms > 0 else 0

    return RequestMetrics(
        ttft_ms=ttft_ms,
        tpot_ms=tpot_ms,
        total_latency_ms=total_ms,
        output_tokens=output_tokens,
        throughput_tps=throughput_tps,
        prompt_tokens=prompt_tokens,
        token_count_source=source,
    )


def compute_stats(metrics: list[RequestMetrics]) -> dict:
    """Compute p50/p95/p99 from a list of RequestMetrics."""
    ttfts = sorted(m.ttft_ms for m in metrics)
    tpots = sorted(m.tpot_ms for m in metrics)
    n = len(ttfts)

    def percentile(sorted_data, p):
        idx = int(p / 100 * n)
        return sorted_data[min(idx, n - 1)]

    return {
        "ttft_p50_ms": percentile(ttfts, 50),
        "ttft_p95_ms": percentile(ttfts, 95),
        "ttft_p99_ms": percentile(ttfts, 99),
        "tpot_p50_ms": percentile(tpots, 50),
        "tpot_p95_ms": percentile(tpots, 95),
        "avg_throughput_tps": statistics.mean(m.throughput_tps for m in metrics),
    }


async def scrape_vllm_metrics(base_url: str) -> dict:
    """
    Scrape Prometheus metrics from vLLM /metrics endpoint.
    Returns dictionary with important keys:
      - kv_cache_usage_pct     : current KV cache usage (0-100)
      - prefix_cache_hits      : cumulative prefix-cache hit tokens (V1 counter)
      - prefix_cache_queries   : cumulative prefix-cache queried tokens (V1 counter)
      - prefix_cache_hit_rate  : hits / queries since server start (0-1)

    Supports vLLM V1 names and the legacy V0 names. vLLM always attaches labels
    (e.g. `{model_name="..."}`), so the metric name is parsed before `{`.
    Values are summed across label sets (e.g. multiple engines).
    """
    metrics_url = base_url.replace("/v1", "") + "/metrics"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(metrics_url)
            text = response.text

        raw: dict[str, float] = {}
        for line in text.splitlines():
            if not line or line.startswith("#"):
                continue
            name = line.split("{", 1)[0].split(" ", 1)[0]
            try:
                value = float(line.rsplit(" ", 1)[-1])
            except ValueError:
                continue
            raw[name] = raw.get(name, 0.0) + value

        result = {}

        # KV cache usage: V1 = kv_cache_usage_perc, V0 (deprecated) = gpu_cache_usage_perc
        for name in ("vllm:kv_cache_usage_perc", "vllm:gpu_cache_usage_perc"):
            if name in raw:
                result["kv_cache_usage_pct"] = raw[name] * 100
                break

        # Prefix cache: V1 exposes hit/query counters, V0 exposed a hit-rate gauge
        hits = raw.get("vllm:prefix_cache_hits_total", raw.get("vllm:prefix_cache_hits"))
        queries = raw.get("vllm:prefix_cache_queries_total", raw.get("vllm:prefix_cache_queries"))
        if hits is not None and queries is not None:
            result["prefix_cache_hits"] = hits
            result["prefix_cache_queries"] = queries
            result["prefix_cache_hit_rate"] = hits / queries if queries > 0 else 0.0
        elif "vllm:gpu_prefix_cache_hit_rate" in raw:
            result["prefix_cache_hit_rate"] = raw["vllm:gpu_prefix_cache_hit_rate"]

        return result
    except Exception as e:
        print(f"[WARN] Could not scrape vLLM metrics: {e}")
        return {}


def save_results(config_name: str, data: dict):
    """Save benchmark results to JSON file."""
    out_file = RESULTS_DIR / f"{config_name}.json"
    with open(out_file, "w") as f:
        json.dump(data, f, indent=2)
    print(f"[✅] Results saved to {out_file}")


# ─── Prompt Templates ───
PROMPTS = {
    "short": "What is the capital of France?",  # ~10 tokens
    "medium": (
        "You are a travel assistant. A customer wants to book a 5-day trip to Japan "
        "including flights from Hanoi, 4-star hotels in Tokyo and Kyoto, a day trip to "
        "Mount Fuji, and all meals. Budget is $3000 per person. The travel dates are "
        "December 20-25. Please provide a detailed itinerary with cost breakdown. "
        * 3  # ~150 tokens
    ),
    "long": (
        # Simulates RAG context — long system prompt typical in the Booking agent
        "You are a helpful travel booking assistant with access to the following hotel "
        "information retrieved from our database:\n\n"
        + ("Hotel Grand Palace: 5-star, central location, price $250/night, "
           "amenities include pool, gym, spa, restaurant. "
           "Customer reviews: excellent service, clean rooms, great breakfast. ") * 25
        + "\n\nBased on the above context, recommend the best hotel for a family of 4 "
          "traveling to this city for a week with a budget of $1500 total for accommodation."
    ),  # ~1800 tokens
}
