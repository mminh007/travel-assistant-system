# app/services/background_tasks/rabbitmq_publisher.py
import json
import asyncio
import aio_pika
from app.core.settings import settings
from app.core.logger import setup_app_logger

logger = setup_app_logger("RabbitMqPublisher")

_connection: aio_pika.RobustConnection | None = None
_conn_lock = asyncio.Lock()

async def get_connection() -> aio_pika.RobustConnection:
    global _connection
    async with _conn_lock:
        if _connection is None or _connection.is_closed:
            for attempt in range(3):
                try:
                    _connection = await aio_pika.connect_robust(settings.rabbitmq.url)
                    break
                except Exception as e:
                    if attempt == 2:
                        logger.error(f"❌ [RabbitMQ Publisher] Failed to connect after 3 attempts: {e}")
                        raise
                    logger.warning(f"⚠️ [RabbitMQ Publisher] Connection failed, retrying in 1s... {e}")
                    await asyncio.sleep(1)
    return _connection

async def publish_extraction_task(user_id: str, session_id: str, target_rag_domain: str):
    """
    Serializes conversation history reference payload and posts it along with its resolved domain routing tag.
    """
    try:
        connection = await get_connection()
        channel = await connection.channel()
        try:

            # 1. Declare Dead Letter Exchange and Dead Letter Queue
            dlx_name = "dlx_memory_exchange"
            dlq_name = "fact_extraction_dlq"
            
            dlx = await channel.declare_exchange(dlx_name, aio_pika.ExchangeType.DIRECT)
            dlq = await channel.declare_queue(dlq_name, durable=True)
            await dlq.bind(dlx, routing_key=dlq_name)
            
            # 2. Declare the main queue and bind it to the DLX
            queue_arguments = {
                "x-dead-letter-exchange": dlx_name,
                "x-dead-letter-routing-key": dlq_name
            }
            await channel.declare_queue(
                settings.rabbitmq.queue_name, 
                durable=True, 
                arguments=queue_arguments
            )
            
            # 🚀 Injected explicit target_rag_domain parameter inside the queue payload envelope
            payload = {
                "codename_process": "FactExtractionProcess",
                "user_id": user_id,
                "session_id": session_id,
                "target_rag_domain": target_rag_domain or "general_memory"
            }
            
            await channel.default_exchange.publish(
                aio_pika.Message(
                    body=json.dumps(payload).encode(),
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT
                ),
                routing_key=settings.rabbitmq.queue_name,
            )
            
            logger.info(f"==> [RabbitMQ] Publish Successfully - Codename: FactExtractionProcess - Assigned Target: {target_rag_domain}\n")
        finally:
            await channel.close()
            
    except Exception as e:
        logger.error(f"❌ [RabbitMQ Publisher Failure] Failed to marshal task parameters: {str(e)}\n")


# ─── Shadow Eval Publisher (Sprint A) ───────────────────────────────────────
# Publishes evaluation payload to the async shadow eval queue after each
# hot-path response. Consumed by shadow_eval_worker running in agent-worker
# Docker service. Skipped for complexity=low to reduce worker overhead.

EVAL_SHADOW_QUEUE = "eval.shadow"
EVAL_SHADOW_DLQ   = "eval_shadow_dlq"
EVAL_SHADOW_DLX   = "dlx_eval_shadow_exchange"


async def publish_shadow_eval(
    session_id: str,
    trace_id: str,
    objective: str,
    executor_output: str,
    findings: list,
    tool_observations: list,
    complexity: str,
) -> None:
    """
    Fire-and-forget publisher for async shadow evaluation.

    Called from node_finding_extractor via asyncio.create_task() — does NOT
    block the hot-path. If this fails, the error is logged but never raised,
    ensuring shadow eval failure is always non-fatal to the user response.

    Args:
        session_id:        Graph session identifier (for Langfuse correlation).
        trace_id:          Langfuse trace ID for score emission.
        objective:         User's original travel objective.
        executor_output:   Raw executor response text (result_summary).
        findings:          Structured findings from node_finding_extractor.
        tool_observations: Raw tool message contents (capped to avoid oversized payloads).
        complexity:        Query complexity tier ('low' | 'medium' | 'high').
    """
    # Skip shadow eval for low-complexity queries — not worth worker overhead.
    # Simple FAQ responses don't need fact-checking or quality scoring.
    if complexity == "low":
        logger.debug(f"[ShadowEval] Skipping for low-complexity query (session={session_id}).")
        return

    payload = {
        "codename_process": "ShadowEvalProcess",
        "session_id": session_id,
        "trace_id": trace_id,
        "objective": objective,
        "executor_output": executor_output,
        "findings": findings,
        # Cap tool observations to avoid oversized payloads in the queue
        "tool_observations": tool_observations[:10],
    }

    try:
        connection = await get_connection()
        channel = await connection.channel()
        try:
            # Declare DLX + DLQ for shadow eval queue
            dlx = await channel.declare_exchange(EVAL_SHADOW_DLX, aio_pika.ExchangeType.DIRECT)
            dlq = await channel.declare_queue(EVAL_SHADOW_DLQ, durable=True)
            await dlq.bind(dlx, routing_key=EVAL_SHADOW_DLQ)

            await channel.declare_queue(
                EVAL_SHADOW_QUEUE,
                durable=True,
                arguments={
                    "x-dead-letter-exchange": EVAL_SHADOW_DLX,
                    "x-dead-letter-routing-key": EVAL_SHADOW_DLQ,
                }
            )
            await channel.default_exchange.publish(
                aio_pika.Message(
                    body=json.dumps(payload, ensure_ascii=False).encode(),
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                ),
                routing_key=EVAL_SHADOW_QUEUE,
            )
            logger.info(f"[ShadowEval] Published eval event — session={session_id} trace={trace_id}")
        finally:
            await channel.close()
    except Exception as e:
        # Non-critical: shadow eval failure must NEVER break the hot-path.
        logger.error(f"[ShadowEval] Publish failed (non-fatal, session={session_id}): {e}")
