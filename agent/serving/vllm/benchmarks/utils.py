"""
Shared utilities for all vLLM & Embedding benchmark scripts.
- Exact TTFT, TPOT, and Inter-Token Latency (ITL) measurement via SSE streaming
- Linear-interpolated percentile calculations (p50, p95, p99)
- Unique prompt salting to prevent unintended prefix-cache hits during baseline/quant/stress tests
- Real-time vLLM /metrics scraping + background polling (KV cache %, waiting queue, preemptions,
  prefix cache hit rate, speculative decoding acceptance rate)
"""
import asyncio
import json
import math
import os
import statistics
import time
import uuid
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional
import httpx

RESULTS_DIR = Path(__file__).parent.parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

DEFAULT_BASE_URL = os.environ.get("VLLM_BASE_URL", "http://localhost:8080/v1")
DEFAULT_EMBEDDING_BASE_URL = os.environ.get("VLLM_EMBEDDING_BASE_URL", "http://localhost:8081/v1")
DEFAULT_MODEL = os.environ.get("VLLM_MODEL", "Qwen/Qwen2.5-3B-Instruct-AWQ")
DEFAULT_EMBEDDING_MODEL = os.environ.get("VLLM_EMBEDDING_MODEL", "Qwen/Qwen3-Embedding-4B")
MAX_MODEL_LEN = int(os.environ.get("VLLM_MAX_CONTEXT_TOKENS", "4096"))


@dataclass
class RequestMetrics:
    ttft_ms: float                        # Time To First Token (ms)
    tpot_ms: float                        # Time Per Output Token (ms) = decode_time / (output_tokens - 1)
    itl_max_ms: float                     # Maximum single inter-token pause (ms) — detects prefill stalls
    total_latency_ms: float               # End-to-end latency (ms)
    output_tokens: int                    # Number of tokens generated
    throughput_tps: float                 # Per-request output tokens / total_s
    decode_tps: float                     # Output tokens / decode_s
    prompt_tokens: Optional[int] = None   # Input tokens (from server usage)
    finish_reason: Optional[str] = None   # "stop" | "length"
    token_count_source: str = "usage"     # "usage" (exact) | "sse_chunks" (fallback)


def percentile_linear(sorted_data: list[float], p: float) -> float:
    """Compute linear-interpolated percentile (matches numpy.percentile(..., method='linear'))."""
    if not sorted_data:
        return 0.0
    n = len(sorted_data)
    if n == 1:
        return float(sorted_data[0])
    pos = (p / 100.0) * (n - 1)
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    frac = pos - lo
    return float(sorted_data[lo] + frac * (sorted_data[hi] - sorted_data[lo]))


def add_prompt_salt(prompt: str, req_idx: Optional[int] = None) -> str:
    """
    Prepend a short unique nonce to the BEGINNING of a prompt so that vLLM's
    automatic prefix cache cannot reuse KV blocks across benchmark requests.
    (Only omit this when explicitly benchmarking prefix cache warm hits.)
    """
    tag = f"[bench-nonce-{req_idx}-{uuid.uuid4().hex[:8]}]\n"
    return tag + prompt


async def measure_streaming_request(
    client: httpx.AsyncClient,
    base_url: str,
    model: str,
    prompt: str,
    max_tokens: int = 200,
    system_prompt: Optional[str] = None,
    ignore_eos: bool = False,
    salt: bool = False,
    req_idx: Optional[int] = None,
) -> RequestMetrics:
    """
    Sends 1 chat completion request to vLLM and measures TTFT, TPOT, max ITL, and throughput.
    Uses SSE streaming to measure exact TTFT (ms when first content token arrives).
    """
    user_content = add_prompt_salt(prompt, req_idx) if salt else prompt
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_content})

    payload: dict = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "stream": True,
        "stream_options": {"include_usage": True},
        "temperature": 0.0,
    }
    if ignore_eos:
        payload["ignore_eos"] = True

    start_time = time.perf_counter()
    first_token_time = None
    last_token_time = None
    prev_token_time = None
    itl_max_ms = 0.0
    chunk_count = 0
    prompt_tokens = None
    completion_tokens = None
    finish_reason = None

    async with client.stream(
        "POST",
        f"{base_url.rstrip('/')}/chat/completions",
        json=payload,
        timeout=180.0,
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

            usage = data.get("usage")
            if usage:
                prompt_tokens = usage.get("prompt_tokens")
                completion_tokens = usage.get("completion_tokens")

            choices = data.get("choices") or []
            if not choices:
                continue
            if choices[0].get("finish_reason"):
                finish_reason = choices[0]["finish_reason"]
            delta = choices[0].get("delta", {}).get("content", "")
            if delta:
                now = time.perf_counter()
                if first_token_time is None:
                    first_token_time = now
                elif prev_token_time is not None:
                    gap_ms = (now - prev_token_time) * 1000.0
                    if gap_ms > itl_max_ms:
                        itl_max_ms = gap_ms
                prev_token_time = now
                last_token_time = now
                chunk_count += 1

    end_time = time.perf_counter()

    if first_token_time is None:
        raise ValueError("No tokens received from vLLM")

    if completion_tokens is not None and completion_tokens > 0:
        output_tokens = completion_tokens
        source = "usage"
    else:
        output_tokens = chunk_count
        source = "sse_chunks"

    ttft_ms = (first_token_time - start_time) * 1000.0
    total_ms = (end_time - start_time) * 1000.0
    decode_s = max(last_token_time - first_token_time, 0.0) if last_token_time else 0.0

    if output_tokens > 1 and decode_s > 0:
        tpot_ms = (decode_s * 1000.0) / (output_tokens - 1)
        decode_tps = (output_tokens - 1) / decode_s
    else:
        tpot_ms = 0.0
        decode_tps = 0.0

    throughput_tps = output_tokens / (total_ms / 1000.0) if total_ms > 0 else 0.0

    return RequestMetrics(
        ttft_ms=ttft_ms,
        tpot_ms=tpot_ms,
        itl_max_ms=itl_max_ms,
        total_latency_ms=total_ms,
        output_tokens=output_tokens,
        throughput_tps=throughput_tps,
        decode_tps=decode_tps,
        prompt_tokens=prompt_tokens,
        finish_reason=finish_reason,
        token_count_source=source,
    )


def compute_stats(metrics: list[RequestMetrics], slo_ttft_ms: float = 1500.0, slo_tpot_ms: float = 60.0) -> dict:
    """Compute p50/p95/p99, token averages, and SLO attainment from RequestMetrics."""
    if not metrics:
        return {
            "ttft_p50_ms": 0.0,
            "ttft_p95_ms": 0.0,
            "ttft_p99_ms": 0.0,
            "tpot_p50_ms": 0.0,
            "tpot_p95_ms": 0.0,
            "tpot_p99_ms": 0.0,
            "itl_max_p95_ms": 0.0,
            "e2e_p50_ms": 0.0,
            "e2e_p95_ms": 0.0,
            "e2e_p99_ms": 0.0,
            "avg_throughput_tps": 0.0,
            "avg_decode_tps": 0.0,
            "avg_prompt_tokens": 0.0,
            "avg_output_tokens": 0.0,
            "slo_attainment_pct": 0.0,
        }

    ttfts = sorted(m.ttft_ms for m in metrics)
    tpots = sorted(m.tpot_ms for m in metrics)
    itls = sorted(m.itl_max_ms for m in metrics)
    e2es = sorted(m.total_latency_ms for m in metrics)
    prompt_toks = [m.prompt_tokens for m in metrics if m.prompt_tokens is not None]
    slo_ok = sum(1 for m in metrics if m.ttft_ms <= slo_ttft_ms and m.tpot_ms <= slo_tpot_ms)

    return {
        "ttft_p50_ms": round(percentile_linear(ttfts, 50), 2),
        "ttft_p95_ms": round(percentile_linear(ttfts, 95), 2),
        "ttft_p99_ms": round(percentile_linear(ttfts, 99), 2),
        "tpot_p50_ms": round(percentile_linear(tpots, 50), 2),
        "tpot_p95_ms": round(percentile_linear(tpots, 95), 2),
        "tpot_p99_ms": round(percentile_linear(tpots, 99), 2),
        "itl_max_p95_ms": round(percentile_linear(itls, 95), 2),
        "e2e_p50_ms": round(percentile_linear(e2es, 50), 2),
        "e2e_p95_ms": round(percentile_linear(e2es, 95), 2),
        "e2e_p99_ms": round(percentile_linear(e2es, 99), 2),
        "avg_throughput_tps": round(statistics.mean(m.throughput_tps for m in metrics), 2),
        "avg_decode_tps": round(statistics.mean(m.decode_tps for m in metrics), 2),
        "avg_prompt_tokens": round(statistics.mean(prompt_toks), 1) if prompt_toks else None,
        "avg_output_tokens": round(statistics.mean(m.output_tokens for m in metrics), 1),
        "slo_attainment_pct": round((slo_ok / len(metrics)) * 100.0, 2),
    }


async def scrape_vllm_metrics(base_url: str) -> dict:
    """
    Scrape Prometheus metrics from vLLM /metrics endpoint.
    Supports both vLLM V1 and legacy V0 metric names.
    """
    metrics_url = base_url.replace("/v1", "").rstrip("/") + "/metrics"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(metrics_url)
            text = response.text

        raw: dict[str, float] = {}
        cache_config: dict[str, str] = {}
        for line in text.splitlines():
            if not line or line.startswith("#"):
                continue
            if line.startswith("vllm:cache_config_info{"):
                labels_part = line.split("{", 1)[1].split("}", 1)[0]
                for pair in labels_part.split(","):
                    if "=" in pair:
                        k, v = pair.split("=", 1)
                        cache_config[k.strip()] = v.strip().strip('"')
            name = line.split("{", 1)[0].split(" ", 1)[0]
            try:
                value = float(line.rsplit(" ", 1)[-1])
            except ValueError:
                continue
            raw[name] = raw.get(name, 0.0) + value

        result: dict = {}
        if cache_config:
            result["cache_config"] = cache_config

        # KV cache usage %
        for name in ("vllm:kv_cache_usage_perc", "vllm:gpu_cache_usage_perc"):
            if name in raw:
                result["kv_cache_usage_pct"] = round(raw[name] * 100.0, 2)
                break

        # Queue & running gauges
        if "vllm:num_requests_running" in raw:
            result["num_requests_running"] = int(raw["vllm:num_requests_running"])
        if "vllm:num_requests_waiting" in raw:
            result["num_requests_waiting"] = int(raw["vllm:num_requests_waiting"])

        # Preemptions counter
        for name in ("vllm:num_preemptions_total", "vllm:num_preemptions"):
            if name in raw:
                result["num_preemptions_total"] = int(raw[name])
                break

        # Prefix cache counters
        hits = raw.get("vllm:prefix_cache_hits_total", raw.get("vllm:prefix_cache_hits"))
        queries = raw.get("vllm:prefix_cache_queries_total", raw.get("vllm:prefix_cache_queries"))
        if hits is not None and queries is not None:
            result["prefix_cache_hits"] = hits
            result["prefix_cache_queries"] = queries
            result["prefix_cache_hit_rate"] = round(hits / queries, 4) if queries > 0 else 0.0
        elif "vllm:gpu_prefix_cache_hit_rate" in raw:
            result["prefix_cache_hit_rate"] = round(raw["vllm:gpu_prefix_cache_hit_rate"], 4)

        # Speculative decoding counters
        spec_accepted = raw.get(
            "vllm:spec_decode_num_accepted_tokens_total",
            raw.get("vllm:spec_decode_num_accepted_tokens"),
        )
        spec_draft = raw.get(
            "vllm:spec_decode_num_draft_tokens_total",
            raw.get("vllm:spec_decode_num_draft_tokens"),
        )
        if spec_accepted is not None and spec_draft is not None and spec_draft > 0:
            result["spec_accepted_tokens"] = spec_accepted
            result["spec_draft_tokens"] = spec_draft
            result["spec_acceptance_rate"] = round(spec_accepted / spec_draft, 4)
        elif "vllm:spec_decode_draft_acceptance_rate" in raw:
            result["spec_acceptance_rate"] = round(raw["vllm:spec_decode_draft_acceptance_rate"], 4)

        return result
    except Exception as e:
        print(f"[WARN] Could not scrape vLLM metrics from {metrics_url}: {e}")
        return {}


class MetricsPoller:
    """
    Background poller that samples vLLM /metrics while a load test is running
    to capture PEAK KV cache usage %, PEAK waiting queue depth, and DELTA preemptions.
    """

    def __init__(self, base_url: str, interval_s: float = 0.5):
        self.base_url = base_url
        self.interval_s = interval_s
        self.samples: list[dict] = []
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()
        self.before: dict = {}
        self.after: dict = {}

    async def __aenter__(self):
        self.before = await scrape_vllm_metrics(self.base_url)
        self._stop.clear()
        self._task = asyncio.create_task(self._poll_loop())
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self._stop.set()
        if self._task:
            await self._task
        self.after = await scrape_vllm_metrics(self.base_url)

    async def _poll_loop(self):
        while not self._stop.is_set():
            snap = await scrape_vllm_metrics(self.base_url)
            if snap:
                self.samples.append(snap)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.interval_s)
            except asyncio.TimeoutError:
                pass

    def summary(self) -> dict:
        kv_vals = [s["kv_cache_usage_pct"] for s in self.samples if "kv_cache_usage_pct" in s]
        wait_vals = [s["num_requests_waiting"] for s in self.samples if "num_requests_waiting" in s]
        run_vals = [s["num_requests_running"] for s in self.samples if "num_requests_running" in s]

        pre_before = self.before.get("num_preemptions_total", 0)
        pre_after = self.after.get("num_preemptions_total", pre_before)

        hit_rate_delta = None
        if "prefix_cache_queries" in self.after and "prefix_cache_queries" in self.before:
            dq = self.after["prefix_cache_queries"] - self.before["prefix_cache_queries"]
            dh = self.after["prefix_cache_hits"] - self.before["prefix_cache_hits"]
            if dq > 0:
                hit_rate_delta = round(dh / dq, 4)

        spec_rate_delta = None
        if "spec_draft_tokens" in self.after and "spec_draft_tokens" in self.before:
            dd = self.after["spec_draft_tokens"] - self.before["spec_draft_tokens"]
            da = self.after["spec_accepted_tokens"] - self.before["spec_accepted_tokens"]
            if dd > 0:
                spec_rate_delta = round(da / dd, 4)

        return {
            "peak_kv_cache_pct": round(max(kv_vals), 2) if kv_vals else self.after.get("kv_cache_usage_pct", 0.0),
            "avg_kv_cache_pct": round(statistics.mean(kv_vals), 2) if kv_vals else 0.0,
            "peak_running_requests": max(run_vals) if run_vals else 0,
            "peak_waiting_requests": max(wait_vals) if wait_vals else 0,
            "preemptions_delta": max(0, pre_after - pre_before),
            "prefix_cache_hit_rate_delta": hit_rate_delta,
            "spec_acceptance_rate_delta": spec_rate_delta,
            "cache_config": self.after.get("cache_config"),
        }


def save_results(config_name: str, data: dict):
    """Save benchmark results to JSON file."""
    data.setdefault("timestamp_utc", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    data.setdefault("max_model_len", MAX_MODEL_LEN)
    out_file = RESULTS_DIR / f"{config_name}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"[OK] Results saved to {out_file}")


# ─── Prompt Templates calibrated for --max-model-len 4096 ───
PROMPTS = {
    "short": (
        "Recommend 3 must-visit attractions in Da Nang, Vietnam for a first-time visitor "
        "and mention the best time of day to visit each."
    ),  # ~30 prompt tokens
    "medium": (
        "You are a travel assistant for BookingAI. A customer wants to book a 5-day trip to Japan "
        "including flights from Hanoi, 4-star hotels in Tokyo and Kyoto, a day trip to "
        "Mount Fuji, and local dining recommendations. Budget is $2500 per person. The travel dates are "
        "December 20-25. Please provide a structured day-by-day itinerary with estimated cost breakdown. "
        * 3
    ),  # ~250 prompt tokens
    "long": (
        # Simulates RAG context + conversation history inside a 4096-token context window
        # (~1800 prompt tokens, leaving ~2200 tokens headroom for completion within max-model-len=4096)
        "You are a helpful travel booking assistant with access to the following retrieved hotel "
        "and itinerary information from our Qdrant hybrid search database:\n\n"
        + (
            "Hotel Grand Palace Da Nang: 5-star beachfront resort on My Khe Beach, price $180/night, "
            "amenities include infinity pool, luxury spa, kids club, airport shuttle, and 3 restaurants. "
            "Verified guest review summary: spotless rooms, attentive staff, generous breakfast buffet, "
            "walking distance to seafood restaurants, 15 minutes from Da Nang International Airport. "
            "Cancellation policy: free cancellation up to 48 hours before check-in.\n"
        )
        * 22
        + "\nBased on the retrieved context above, recommend the best accommodation strategy and "
        "5-day schedule for a family of 4 (2 adults, 2 children aged 6 and 10) with a total "
        "accommodation budget of $1200."
    ),  # ~1800 prompt tokens (safe for --max-model-len 4096)
}
