# app/bootstrap/health.py
"""
Pre-startup health checks for external dependencies.
Fail fast with clear error messages rather than silent runtime failures.
"""
import httpx
from app.core.settings import settings
from app.core.logger import setup_app_logger

logger = setup_app_logger("HealthCheck")

async def ping_llm_provider() -> None:
    """
    Ping the active LLM provider endpoint to verify reachability.
    Logs a warning on failure — does NOT raise (agent degrades gracefully).
    """
    provider = settings.llm_provider

    if provider == "vllm":
        url = f"{settings.vllm.base_url.rstrip('/v1')}/health"
        label = f"vLLM @ {settings.vllm.base_url}"
    else:
        url = f"{settings.nine_router.base_url.rstrip('/v1')}/health"
        label = f"9Router @ {settings.nine_router.base_url}"

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(url)
            if r.status_code < 500:
                logger.info(f"==> [HealthCheck] {label} — REACHABLE (HTTP {r.status_code})")
            else:
                logger.warning(f"⚠️ [HealthCheck] {label} returned HTTP {r.status_code} — provider may be degraded")
    except Exception as e:
        logger.warning(
            f"⚠️ [HealthCheck] Cannot reach {label}: {e}\n"
            f"    Agent will start but LLM calls will fail until provider is available."
        )


async def ping_redis() -> None:
    """Verify Redis connectivity at startup."""
    import redis.asyncio as redis_async
    try:
        r = redis_async.from_url(settings.redis.url)
        await r.ping()
        await r.aclose()
        logger.info(f"==> [HealthCheck] Redis @ {settings.redis.url} — REACHABLE")
    except Exception as e:
        logger.warning(f"⚠️ [HealthCheck] Redis unreachable: {e}")
