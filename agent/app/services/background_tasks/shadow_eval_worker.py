# app/services/background_tasks/shadow_eval_worker.py
"""
Shadow Eval Worker -- Consumer for the async eval.shadow RabbitMQ queue.

Runs in the dedicated agent-worker Docker service (not in agent-api).
Calls node_fact_checker + node_evaluator_agent as plain async functions
(no graph overhead) on the payload published by node_finding_extractor.

Scores are forwarded to Langfuse via the existing emit mechanism inside
node_evaluator_agent. Worker failure is fully isolated from the hot-path.
"""
import asyncio
import hashlib
import json
import aio_pika

from app.core.settings import settings
from app.core.logger import setup_app_logger
from app.graph.nodes.evaluator import node_fact_checker, node_evaluator_agent

logger = setup_app_logger("ShadowEvalWorker")

EVAL_SHADOW_QUEUE = "eval.shadow"
EVAL_SHADOW_DLQ   = "eval_shadow_dlq"
EVAL_SHADOW_DLX   = "dlx_eval_shadow_exchange"


def _should_sample_for_ragas(session_id: str, rate: float = 0.05) -> bool:
    """
    Deterministic 5pct sampling via MD5 hash.
    Same session_id always produces the same sampling decision.
    Sprint B placeholder -- Ragas runner will be wired here.
    """
    return (int(hashlib.md5(session_id.encode()).hexdigest(), 16) % 100) < int(rate * 100)


async def process_eval_event(payload: dict) -> None:
    """
    Core evaluation pipeline for a single shadow eval payload.
    Builds a minimal state dict and calls fact_checker + evaluator_agent.
    """
    session_id = payload.get("session_id", "unknown")
    logger.info("[ShadowEval] Processing eval event for session=%s", session_id)

    mock_state = {
        "messages": [],
        "extracted_findings": payload.get("findings", []),
        "raw_executor_output": payload.get("executor_output", ""),
        "objective": payload.get("objective", ""),
        "action_history": [],
        "rework_count": 0,
        "langfuse_trace_id": payload.get("trace_id", ""),
        "session_id": session_id,
    }

    try:
        fc_result = await node_fact_checker(mock_state)
        mock_state.update(fc_result)
        eval_result = await node_evaluator_agent(mock_state)
        logger.info(
            "[ShadowEval] Done session=%s tool=%s evidence=%s citation=%s freshness=%s",
            session_id,
            eval_result.get("tool_quality_score"),
            eval_result.get("evidence_quality_score"),
            eval_result.get("citation_quality_score"),
            eval_result.get("freshness_score"),
        )
        # Sprint B: Ragas 5pct sampling hook
        if _should_sample_for_ragas(session_id):
            logger.info("[ShadowEval] Session %s selected for Ragas sampling (Sprint B).", session_id)
    except Exception as e:
        logger.error("[ShadowEval] Pipeline failed for session=%s: %s", session_id, e)


async def run_shadow_eval_worker() -> None:
    """Main consumer loop for the eval.shadow queue."""
    logger.info("[ShadowEvalWorker] Starting consumer on queue eval.shadow...")
    max_retries = 5
    for attempt in range(max_retries):
        try:
            connection = await aio_pika.connect_robust(settings.rabbitmq.url)
            break
        except Exception as e:
            if attempt == max_retries - 1:
                logger.error("[ShadowEvalWorker] Failed to connect after %d attempts: %s", max_retries, e)
                raise
            logger.warning("[ShadowEvalWorker] RabbitMQ not ready (attempt %d/%d), retrying in 5s...", attempt + 1, max_retries)
            await asyncio.sleep(5)

    channel = await connection.channel()
    await channel.set_qos(prefetch_count=1)

    dlx = await channel.declare_exchange(EVAL_SHADOW_DLX, aio_pika.ExchangeType.DIRECT)
    dlq = await channel.declare_queue(EVAL_SHADOW_DLQ, durable=True)
    await dlq.bind(dlx, routing_key=EVAL_SHADOW_DLQ)

    queue = await channel.declare_queue(
        EVAL_SHADOW_QUEUE,
        durable=True,
        arguments={
            "x-dead-letter-exchange": EVAL_SHADOW_DLX,
            "x-dead-letter-routing-key": EVAL_SHADOW_DLQ,
        }
    )

    async def _on_message(message: aio_pika.IncomingMessage) -> None:
        async with message.process():
            try:
                payload = json.loads(message.body.decode())
                await process_eval_event(payload)
            except Exception as e:
                logger.error("[ShadowEvalWorker] Message processing error: %s", e)

    await queue.consume(_on_message)
    logger.info("[ShadowEvalWorker] Consumer active on eval.shadow.")
