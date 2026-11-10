# app/services/background_tasks/llm_worker.py
"""
LLM Worker Consumer — Consumer for the llm.requests RabbitMQ priority queue.

Runs inside the existing agent-worker Docker service (same process as the
fact_extraction, hotel_sync, and shadow_eval consumers in worker_main.py).

Design principles:
- prefetch_count = tier2_semaphore: the worker pulls exactly as many
  messages as vLLM can concurrently handle.  This is the natural
  back-pressure mechanism — the queue accumulates surplus without OOM.
- The asyncio Semaphore guard is KEPT inside invoke_llm_with_limit()
  (called via graph/config.py).  It acts as a final safety net in case
  multiple worker instances are temporarily running (e.g. rolling restart).
- Each job result is written to Redis with a TTL so the gRPC handler can
  stream it back to the client via wait_for_job() / PollJobResult RPC.
- Worker failure is fully isolated: a crash here does not affect the
  hot-path (fact_extraction, hotel_sync, shadow_eval consumers).
"""
import asyncio
import json
import time

import aio_pika
from redis.asyncio import Redis

from app.core.settings import settings
from app.core.logger import setup_app_logger
from app.core.concurrency import _CONCURRENCY
from app.graph.config import invoke_llm_with_limit, get_llm_instance
from app.services.job_result_store import set_job_result, set_job_status
from app.core.metrics import LLM_QUEUE_WAIT_SECONDS, LLM_JOB_PROCESSED_TOTAL

logger = setup_app_logger("LlmWorker")


async def process_llm_job(payload: dict, redis: Redis) -> None:
    """
    Core processing logic for a single dequeued LLM job.

    Calls invoke_llm_with_limit() which internally manages:
    - asyncio Semaphore (vLLM concurrency guard)
    - Tenacity retry on HTTP 429 / transient errors
    - Prometheus LLM call metrics

    On completion, writes result to Redis for the gRPC handler to retrieve.
    """
    job_id      = payload["job_id"]
    session_id  = payload["session_id"]
    tier        = payload.get("tier", 2)
    messages    = payload["messages"]
    priority    = payload.get("priority", 2)
    enqueued_at = payload.get("enqueued_at", time.time())

    # Measure how long this job waited in the queue before being picked up
    queue_wait = time.time() - enqueued_at
    LLM_QUEUE_WAIT_SECONDS.labels(priority=str(priority)).observe(queue_wait)

    await set_job_status(redis, job_id, "processing")
    logger.info(
        "[LlmWorker] Processing job=%s session=%s tier=%d queue_wait=%.2fs",
        job_id, session_id, tier, queue_wait,
    )

    try:
        llm = get_llm_instance(tier)
        response, token_usage = await invoke_llm_with_limit(
            tier=tier,
            llm=llm,
            messages=messages,
            node_name="llm_worker",
        )
        result = {
            "job_id":        job_id,
            "session_id":    session_id,
            "content":       response.content,
            "status":        "done",
            "input_tokens":  token_usage.input_tokens,
            "output_tokens": token_usage.output_tokens,
            "completed_at":  time.time(),
        }
        await set_job_result(redis, job_id, result)
        LLM_JOB_PROCESSED_TOTAL.labels(status="ok").inc()
        logger.info(
            "[LlmWorker] Done job=%s output_tokens=%d",
            job_id, token_usage.output_tokens,
        )

    except Exception as exc:
        LLM_JOB_PROCESSED_TOTAL.labels(status="error").inc()
        logger.error("[LlmWorker] Failed job=%s: %s", job_id, exc)
        await set_job_result(redis, job_id, {
            "job_id":       job_id,
            "session_id":   session_id,
            "status":       "error",
            "error":        str(exc),
            "completed_at": time.time(),
        })


async def run_llm_worker(redis: Redis) -> None:
    """
    Main consumer loop for the llm.requests priority queue.

    Sets QoS prefetch_count = tier2_semaphore so the worker never pulls
    more messages from the queue than vLLM can process concurrently.
    This provides natural back-pressure without additional coordination.

    Args:
        redis: Shared async Redis client injected from worker_main.py.
               The client lifetime is managed by the caller.
    """
    logger.info("[LlmWorker] Starting consumer on queue '%s'...", settings.rabbitmq.llm_requests_queue)

    # Retry connection with exponential back-off (same pattern as shadow_eval_worker)
    max_retries = 5
    for attempt in range(max_retries):
        try:
            connection = await aio_pika.connect_robust(settings.rabbitmq.url)
            break
        except Exception as exc:
            if attempt == max_retries - 1:
                logger.error(
                    "[LlmWorker] Failed to connect after %d attempts: %s",
                    max_retries, exc,
                )
                raise
            logger.warning(
                "[LlmWorker] RabbitMQ not ready (attempt %d/%d), retrying in 5s…",
                attempt + 1, max_retries,
            )
            await asyncio.sleep(5)

    channel = await connection.channel()

    # prefetch = tier2_semaphore: worker won't pull more than vLLM can handle
    _cfg = _CONCURRENCY.get(settings.llm_provider, {"tier1": 4, "tier2": 2})
    prefetch = _cfg["tier2"]
    await channel.set_qos(prefetch_count=prefetch)

    # Redeclare queue and DLX/DLQ (idempotent — must match publisher declaration)
    dlx = await channel.declare_exchange(
        settings.rabbitmq.llm_requests_dlx,
        aio_pika.ExchangeType.DIRECT,
    )
    dlq = await channel.declare_queue(
        settings.rabbitmq.llm_requests_dlq,
        durable=True,
    )
    await dlq.bind(dlx, routing_key=settings.rabbitmq.llm_requests_dlq)

    queue = await channel.declare_queue(
        settings.rabbitmq.llm_requests_queue,
        durable=True,
        arguments={
            "x-max-priority":            settings.rabbitmq.llm_max_priority,
            "x-dead-letter-exchange":    settings.rabbitmq.llm_requests_dlx,
            "x-dead-letter-routing-key": settings.rabbitmq.llm_requests_dlq,
        },
    )

    async def _on_message(message: aio_pika.IncomingMessage) -> None:
        """
        AMQP message callback.  Uses message.process() context manager so:
        - ACK is sent automatically on clean exit
        - NACK (requeue=False → DLQ) is sent on unhandled exception
        """
        async with message.process():
            try:
                payload = json.loads(message.body.decode())
                await process_llm_job(payload, redis)
            except Exception as exc:
                logger.error("[LlmWorker] Message processing error: %s", exc)
                # Exception propagates out of message.process() → NACK → DLQ

    await queue.consume(_on_message)
    logger.info(
        "[LlmWorker] Consumer active on '%s' (prefetch=%d).",
        settings.rabbitmq.llm_requests_queue, prefetch,
    )
