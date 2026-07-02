# app/core/concurrency.py
"""
Global rate-limit guards for GitHub Models (and compatible providers).
GitHub Models High tier: 10 RPM, 50 RPD, 2 concurrent requests.
"""
import asyncio

# Hard limit matching GitHub Models High tier concurrent request cap
TIER2_SEMAPHORE = asyncio.Semaphore(2)

# Tier 1 (fast models) has higher concurrency — conservative at 4
TIER1_SEMAPHORE = asyncio.Semaphore(4)

def get_semaphore(tier: int) -> asyncio.Semaphore:
    return TIER2_SEMAPHORE if tier >= 2 else TIER1_SEMAPHORE
