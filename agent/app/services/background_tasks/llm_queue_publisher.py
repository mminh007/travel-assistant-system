# app/services/background_tasks/llm_queue_publisher.py
"""
LLM Queue Publisher — Enqueues LLM graph jobs into the RabbitMQ priority queue.

Design:
- Reuses get_connection() from rabbitmq_publisher to share the singleton
  connection pool. No second connection is opened for the same process.
- Priority levels:
    3 (HIGH)   — Premium / authenticated users, retried jobs
    2 (NORMAL) — Standard authenticated requests
    1 (LOW)    — Anonymous users, background batch tasks
- Queue is declared with x-max-priority=3 and a Dead Letter Exchange so
  undeliverable messages are routed to llm_requests_dlq for inspection.
- Callers receive a job_id and are responsible for polling/subscribing via
  JobResultStore (services/job_result_store.py).
"""
import json
import time
from uuid import uuid4

import aio_pika

from app.core.settings import settings
from app.core.logger import setup_app_logger
# Reuse the singleton connection pool from the existing publisher
from app.services.background_tasks.rabbitmq_publisher import get_connection

logger = setup_app_logger("LlmQueuePublisher")


async def enqueue_llm_request(
    session_id: str,
    user_id: str,
    messages: list,
    tier: int,
    priority: int = 2,
    extra_state: dict = None,
) -> str:
    """
    Enqueue a full LLM graph job into the RabbitMQ priority queue.

    Args:
        session_id:  LangGraph / Redis thread identifier.
        user_id:     Authenticated user ID (or anon_ prefix for anonymous).
        messages:    List of LangChain message dicts to pass to the LLM.
        tier:        LLM tier (1=fast, 2=balanced). Passed through to worker.
        priority:    Queue priority (1=low, 2=normal, 3=high). Higher value
                     means the message is dequeued first by RabbitMQ.
        extra_state: Optional extra graph-state fields forwarded to the worker
                     (e.g. current_domain, complexity).

    Returns:
        job_id: Unique identifier for this job. Use with JobResultStore to
                retrieve the result once the worker completes processing.
    """
    job_id = f"{session_id}_{uuid4().hex[:8]}"
    payload = {
        "job_id":      job_id,
        "session_id":  session_id,
        "user_id":     user_id,
        "messages":    messages,
        "tier":        tier,
        "priority":    priority,
        "enqueued_at": time.time(),
        "extra_state": extra_state or {},
    }

    connection = await get_connection()
    channel = await connection.channel()
    try:
        # Declare DLX + DLQ (idempotent — safe to call on every publish)
        dlx = await channel.declare_exchange(
            settings.rabbitmq.llm_requests_dlx,
            aio_pika.ExchangeType.DIRECT,
        )
        dlq = await channel.declare_queue(
            settings.rabbitmq.llm_requests_dlq,
            durable=True,
        )
        await dlq.bind(dlx, routing_key=settings.rabbitmq.llm_requests_dlq)

        # Declare the priority queue itself (idempotent)
        await channel.declare_queue(
            settings.rabbitmq.llm_requests_queue,
            durable=True,
            arguments={
                "x-max-priority":            settings.rabbitmq.llm_max_priority,
                "x-dead-letter-exchange":    settings.rabbitmq.llm_requests_dlx,
                "x-dead-letter-routing-key": settings.rabbitmq.llm_requests_dlq,
            },
        )

        await channel.default_exchange.publish(
            aio_pika.Message(
                body=json.dumps(payload, ensure_ascii=False).encode(),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                priority=priority,
            ),
            routing_key=settings.rabbitmq.llm_requests_queue,
        )
        logger.info(
            "[LlmQueue] Enqueued job=%s session=%s user=%s tier=%d priority=%d",
            job_id, session_id, user_id, tier, priority,
        )
        return job_id

    except Exception as e:
        logger.error("[LlmQueue] Failed to enqueue job for session=%s: %s", session_id, e)
        raise
    finally:
        await channel.close()
