# app/services/job_result_store.py
"""
Job Result Store — Thin async Redis wrapper for LLM job state and results.

Lifecycle of a job:
    1. gRPC handler enqueues job → status set to "queued"
    2. Worker picks up message  → status set to "processing"
    3. Worker completes / fails → status set to "done" / "error",
                                  result JSON written to result key
    4. gRPC handler polls       → reads result key, streams content to client
    5. TTL expires (default 300s) → both keys auto-deleted by Redis

Key schema:
    llm_status:{job_id}  → "queued" | "processing" | "done" | "error"
    llm_result:{job_id}  → JSON blob (see set_job_result for shape)
"""
import asyncio
import json
import time

from redis.asyncio import Redis

from app.core.settings import settings
from app.core.logger import setup_app_logger

logger = setup_app_logger("JobResultStore")

_RESULT_PREFIX = "llm_result:"
_STATUS_PREFIX = "llm_status:"


async def set_job_status(redis: Redis, job_id: str, status: str, ttl: int = None) -> None:
    """Write or refresh the status key for a job."""
    ttl = ttl or settings.rabbitmq.llm_result_ttl
    await redis.setex(f"{_STATUS_PREFIX}{job_id}", ttl, status)


async def set_job_result(redis: Redis, job_id: str, result: dict, ttl: int = None) -> None:
    """
    Persist the final result dict and flip status to 'done' / 'error'.

    Expected result shape (produced by llm_worker.py):
        {
            "job_id":        str,
            "session_id":    str,
            "content":       str,   # LLM response text
            "status":        "done" | "error",
            "error":         str,   # only present on error
            "input_tokens":  int,
            "output_tokens": int,
            "completed_at":  float,
        }
    """
    ttl = ttl or settings.rabbitmq.llm_result_ttl
    await redis.setex(
        f"{_RESULT_PREFIX}{job_id}",
        ttl,
        json.dumps(result, ensure_ascii=False),
    )
    await redis.setex(
        f"{_STATUS_PREFIX}{job_id}",
        ttl,
        result.get("status", "done"),
    )


async def get_job_result(redis: Redis, job_id: str) -> dict | None:
    """Return the result dict if available, else None."""
    raw = await redis.get(f"{_RESULT_PREFIX}{job_id}")
    return json.loads(raw) if raw else None


async def get_job_status(redis: Redis, job_id: str) -> str | None:
    """Return the current status string, or None if the key has expired."""
    raw = await redis.get(f"{_STATUS_PREFIX}{job_id}")
    return raw.decode() if raw else None


async def wait_for_job(
    redis: Redis,
    job_id: str,
    timeout: float = 120.0,
    poll_interval: float = 0.5,
) -> dict | None:
    """
    Poll Redis for a job result until it appears or timeout is reached.

    Used by the gRPC handler to stream the final response back to the client
    after enqueuing the request.  Uses asyncio.sleep() so the event loop
    remains free to serve other coroutines while waiting.

    Args:
        redis:         Async Redis client (caller-owned, not closed here).
        job_id:        Job identifier returned by enqueue_llm_request().
        timeout:       Maximum seconds to wait before returning None.
        poll_interval: Seconds between Redis GET attempts (default 0.5s).

    Returns:
        Result dict on success, None on timeout.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = await get_job_result(redis, job_id)
        if result is not None:
            return result
        await asyncio.sleep(poll_interval)
    logger.warning("[JobResultStore] Timeout waiting for job=%s (%.0fs)", job_id, timeout)
    return None
