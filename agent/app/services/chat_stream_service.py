# app/services/chat_stream_service.py
import hashlib
import time
import json
import asyncio
from typing import AsyncIterator, Tuple, Optional, Any
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.redis.aio import AsyncRedisSaver
from langfuse.langchain import CallbackHandler
from langchain_core.tracers import LangChainTracer
import app.core.logger as logger
from app.core.settings import settings
from app.core.asymmetric_helper import sign_data_es256
from app.bootstrap.container import container
from app.graph.workflow import agent_graph
from app.services.rabbitmq_publisher import publish_extraction_task

logger_instance = logger.setup_app_logger("ChatStreamService")

class ChatStreamService:
    def __init__(self, bg_tasks: Optional[set] = None):
        self.graph = agent_graph
        self._bg_tasks = bg_tasks if bg_tasks is not None else set()

    def generate_receipt(self, session_id: str, ai_full_response_text: str) -> dict:
        response_hash = hashlib.sha256(ai_full_response_text.encode('utf-8')).hexdigest()
        timestamp = int(time.time())
        data_to_sign = f"{session_id}:{timestamp}:{response_hash}"
        signature = sign_data_es256(data_to_sign, settings.security.ai_receipt_private_key.get_secret_value())
        
        return {
            "type": "receipt",
            "session_id": session_id,
            "timestamp": timestamp,
            "response_hash": response_hash,
            "signature": signature,
            "key_id": "secp256r1-default-key"
        }

    async def stream(
        self,
        user_id: str,
        session_id: str,
        prompt: str,
        llm_provider: Optional[str] = None,
        api_key: Optional[str] = None,
        is_cancelled_callback=None,
        source: str = "http",
    ) -> AsyncIterator[Tuple[str, Any]]:
        # Semantic cache
        try:
            cached_reply = await container.semantic_cache.get(prompt)
            if cached_reply:
                yield "chunk", cached_reply
                return
        except Exception as cache_err:
            logger_instance.warning(f"==> [StreamService] Semantic cache lookup failed: {cache_err}")

        initial_state = {
            "messages": [HumanMessage(content=prompt)],
            "user_id": user_id,
            "session_id": session_id,
            "current_domain": "general_memory" if source == "http" else "travel",
            "complexity": "medium",
            "required_agents": [],
            "iteration_count": 0,
            "tool_call_count": 0,
            "action_history": [],
            "rework_count": 0,
            "tasks": [],
            "current_task_id": None,
        }

        trace_config = {
            "metadata": {
                "session_id": session_id, 
                "user_id": user_id,
                "source": source
            },
            "configurable": {
                "thread_id": f"{user_id}_{session_id}",
                "llm_provider": llm_provider,
                "api_key": api_key
            }
        }

        langfuse_handler = None
        langsmith_tracer = None
        if source == "http":
            langfuse_handler = CallbackHandler(
                session_id=session_id,
                user_id=user_id,
                tags=["prod-stream"]
            )
            langsmith_tracer = LangChainTracer(project_name="agent-ecosystem-prod")
            trace_config["callbacks"] = [langfuse_handler, langsmith_tracer]

        is_anonymous = user_id.startswith("anon_")
        final_state_messages = []
        ai_full_response_text = ""
        resolved_domain = initial_state["current_domain"]

        async def run_graph_stream(graph_instance):
            nonlocal ai_full_response_text, final_state_messages, resolved_domain
            async for event in graph_instance.astream_events(initial_state, version="v2", config=trace_config):
                if is_cancelled_callback and is_cancelled_callback():
                    logger_instance.info("==> [StreamService] Stream dropped by upstream.")
                    break
                
                kind = event["event"]
                
                if kind == "on_chat_model_stream":
                    current_node = event.get("metadata", {}).get("langgraph_node", "")
                    if current_node not in ["final_synthesizer", "out_of_domain"]:
                        continue
                    content = event["data"]["chunk"].content
                    if content and isinstance(content, str):
                        ai_full_response_text += content
                        yield "chunk", content
                        
                elif kind == "on_chat_model_end":
                    current_node = event.get("metadata", {}).get("langgraph_node", "")
                    if current_node in ["final_synthesizer", "out_of_domain"]:
                        output = event.get("data", {}).get("output")
                        if output and hasattr(output, "response_metadata"):
                            finish_reason = output.response_metadata.get("finish_reason")
                            if finish_reason in ("length", "max_tokens"):
                                logger_instance.warning(f"⚠️ [TOKEN LIMIT EXCEEDED] max_completion_tokens exceeded in {current_node}")

                elif kind == "on_chain_end" and event["name"] == "agent_graph":
                    output_payload = event["data"]["output"]
                    final_state_messages = output_payload["messages"]
                    resolved_domain = output_payload.get("current_domain", resolved_domain)
                    
                    if not ai_full_response_text and final_state_messages:
                        last_msg = final_state_messages[-1]
                        if getattr(last_msg, "type", "") == "ai" and last_msg.content and isinstance(last_msg.content, str):
                            ai_full_response_text += last_msg.content
                            yield "chunk", last_msg.content

        try:
            if is_anonymous:
                graph_run = self.graph.compile(name="agent_graph")
                async for event_type, chunk in run_graph_stream(graph_run):
                    yield event_type, chunk
            else:
                async with AsyncRedisSaver(redis_url=settings.redis.url) as saver:
                    graph_run = self.graph.compile(checkpointer=saver, name="agent_graph")
                    async for event_type, chunk in run_graph_stream(graph_run):
                        yield event_type, chunk

            if final_state_messages and not is_anonymous:
                task = asyncio.create_task(publish_extraction_task(user_id, session_id, resolved_domain))
                self._bg_tasks.add(task)
                task.add_done_callback(self._bg_tasks.discard)

            if ai_full_response_text:
                try:
                    await container.semantic_cache.set(prompt, ai_full_response_text)
                except Exception as cache_err:
                    logger_instance.warning(f"==> [StreamService] Semantic cache write failed: {cache_err}")
                
                receipt = self.generate_receipt(session_id, ai_full_response_text)
                yield "receipt", receipt

        except Exception as e:
            logger_instance.error(f"==> [StreamService] Runtime exception: {str(e)}")
            yield "error", str(e)
        finally:
            if langfuse_handler:
                langfuse_handler.flush()
