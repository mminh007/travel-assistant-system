# app/services/rabbitmq_publisher.py
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
