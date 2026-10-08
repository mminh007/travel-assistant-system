# app/core/concurrency.py
"""
Global rate-limit guards for GitHub Models (and compatible providers).
GitHub Models High tier: 10 RPM, 50 RPD, 2 concurrent requests.
"""
import asyncio
from app.core.settings import settings

"""
Global concurrency guards — tuned per active LLM provider.

9Router  (OpenAI-compatible proxy): No strict hard concurrency limit.
          Tier2=8 allows healthy parallelism without overwhelming upstream.
vLLM     (self-hosted single GPU):  Batching handles concurrency natively.
          Tier2=4 avoids OOM on smaller GPUs (7B model).
claude   (Anthropic direct):        Tier2=2 to respect Anthropic rate limits.

These values are intentionally conservative. Tune upward after load testing.
"""

_CONCURRENCY = {
    "nine_router": {"tier1": 8, "tier2": 8},
    "vllm":        {"tier1": 12, "tier2": 4},
    "claude":      {"tier1": 4,  "tier2": 2},
}

_cfg = _CONCURRENCY.get(settings.llm_provider, {"tier1": 4, "tier2": 2})

TIER2_SEMAPHORE = asyncio.Semaphore(_cfg["tier2"])
TIER1_SEMAPHORE = asyncio.Semaphore(_cfg["tier1"])

def get_semaphore(tier: int) -> asyncio.Semaphore:
    return TIER2_SEMAPHORE if tier >= 2 else TIER1_SEMAPHORE
