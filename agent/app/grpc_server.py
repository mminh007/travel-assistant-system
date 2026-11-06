# app/grpc_server.py
import asyncio
import grpc
from grpc import aio
import sys
import os
import json
import hashlib
import time

sys.path.append(os.path.join(os.path.dirname(__file__), "grpc_layer"))
import chat_pb2
import chat_pb2_grpc
from langchain_core.messages import HumanMessage
from app.services.background_tasks.rabbitmq_publisher import publish_extraction_task
from app.core.logger import setup_app_logger
from app.graph import workflow
from langgraph.checkpoint.redis.aio import AsyncRedisSaver
from app.core.settings import settings
from app.mcp.mcp_client import mcp_manager
from app.bootstrap.startup import startup, shutdown
from app.bootstrap.container import container
from app.core.helpers.asymmetric_helper import sign_data_es256
from app.core.helpers.crypto_helper import encrypt_value, decrypt_value
from app.services.streaming.chat_stream_service import ChatStreamService
from app.services.job_result_store import wait_for_job
from redis.asyncio import Redis as AsyncRedis

from prometheus_client import start_http_server
from app.core.metrics import GRPC_ACTIVE_STREAMS, GRPC_ERRORS_TOTAL

logger = setup_app_logger("GrpcServerCore")

class AgentServiceServicer(chat_pb2_grpc.AgentServiceServicer):
    def __init__(self):
        self.graph = workflow.agent_graph
        self._bg_tasks = set()

    async def StreamChat(self, request: chat_pb2.ChatRequest, context: grpc.aio.ServicerContext):
        if len(request.prompt) > 8000:
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details("Prompt exceeds maximum length of 8000 characters")
            yield chat_pb2.ChatResponse()
            return
            
        metadata = context.invocation_metadata()
        correlation_id = "N/A"
        if metadata:
            for key, value in metadata:
                if key == "x-correlation-id":
                    correlation_id = value
                    break

        logger.info(f"==> [gRPC] Received request from User: {request.user_id}, Session: {request.session_id}, CorrelationId: {correlation_id}")

        # 🚀 METRIC: Increment active stream gauge (semantic cache lookup is handled in ChatStreamService.stream)
        GRPC_ACTIVE_STREAMS.inc()

        try:
            chat_service = ChatStreamService(bg_tasks=self._bg_tasks)
            async for event_type, data in chat_service.stream(
                user_id=request.user_id,
                session_id=request.session_id,
                prompt=request.prompt,
                is_cancelled_callback=context.cancelled,
                source="grpc"
            ):
                if event_type == "chunk":
                    yield chat_pb2.ChatResponse(chunk=data)
                elif event_type == "receipt":
                    receipt_msg = chat_pb2.Receipt(
                        session_id=data["session_id"],
                        timestamp=data["timestamp"],
                        response_hash=data["response_hash"],
                        signature=data["signature"],
                        key_id=data["key_id"]
                    )
                    yield chat_pb2.ChatResponse(chunk="", receipt=receipt_msg)
                    logger.info(f"==> [gRPC Receipt] Successfully generated and yielded AI Response Receipt for Session: {request.session_id}")
                elif event_type == "error":
                    # Surface errors as gRPC status internal
                    logger.error(f"==> [gRPC] Error from ChatStreamService: {data}")
                    context.set_code(grpc.StatusCode.INTERNAL)
                    context.set_details(data)

        except Exception as e:
            GRPC_ERRORS_TOTAL.inc()
            logger.error(f"==> [gRPC Error] Runtime exception caught in pipeline: {str(e)}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))

        finally:
            # METRIC: Decrement stream gauge upon termination
            GRPC_ACTIVE_STREAMS.dec()

    async def PollJobResult(
        self,
        request: chat_pb2.PollJobRequest,
        context: grpc.aio.ServicerContext,
    ):
        """
        Option C: Stream the result of an async LLM job back to the client.

        The client calls this RPC after receiving a "queued" event (with a
        job_id) from StreamChat when settings.use_llm_queue = True.

        Behaviour:
        - Polls Redis every 500ms for up to 120s waiting for the LLM worker
          to write the result.
        - Yields a single ChatResponse chunk when the job completes.
        - Returns DEADLINE_EXCEEDED if the job is still pending after 120s.
        - Returns INTERNAL if the worker reported an error.

        Args:
            request.job_id:  Identifier returned in the StreamChat queued event.
            request.user_id: Used by UserOwnershipInterceptor for auth checks.
        """
        job_id = request.job_id
        logger.info("==> [gRPC PollJobResult] Polling job_id=%s user=%s", job_id, request.user_id)

        async with AsyncRedis.from_url(settings.redis.url) as redis:
            result = await wait_for_job(redis, job_id, timeout=120.0)

        if result is None:
            context.set_code(grpc.StatusCode.DEADLINE_EXCEEDED)
            context.set_details(
                f"Job {job_id} did not complete within 120s. "
                "The worker may be overloaded — retry shortly."
            )
            yield chat_pb2.ChatResponse()
            return

        if result.get("status") == "error":
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(result.get("error", "LLM worker error"))
            yield chat_pb2.ChatResponse()
            return

        content_text = result.get("content", "")
        logger.info(
            "==> [gRPC PollJobResult] Done job_id=%s tokens_out=%s",
            job_id, result.get("output_tokens", "?"),
        )
        yield chat_pb2.ChatResponse(chunk=content_text)

from app.grpc_layer.auth_interceptor import UserOwnershipInterceptor

async def serve():
    await asyncio.to_thread(start_http_server, 8001)
    logger.info("📊 gRPC Prometheus metrics exporter server listening securely on port 8001\n")

    await startup()
    
    server = aio.server(interceptors=[UserOwnershipInterceptor()])
    chat_pb2_grpc.add_AgentServiceServicer_to_server(AgentServiceServicer(), server)
    listen_addr = '[::]:50051'
    
    if settings.grpc.tls_enabled:
        if not os.path.exists(settings.grpc.tls_cert_path) or not os.path.exists(settings.grpc.tls_key_path):
            raise FileNotFoundError(f"TLS enabled but certificate or key file not found at '{settings.grpc.tls_cert_path}' or '{settings.grpc.tls_key_path}'")
        
        with open(settings.grpc.tls_key_path, 'rb') as f:
            private_key = f.read()
        with open(settings.grpc.tls_cert_path, 'rb') as f:
            certificate_chain = f.read()
            
        if settings.grpc.tls_ca_cert_path:
            if not os.path.exists(settings.grpc.tls_ca_cert_path):
                raise FileNotFoundError(f"TLS CA certificate file not found at '{settings.grpc.tls_ca_cert_path}'")
            with open(settings.grpc.tls_ca_cert_path, 'rb') as f:
                root_certificates = f.read()
            server_credentials = grpc.ssl_server_credentials(
                ((private_key, certificate_chain),),
                root_certificates=root_certificates,
                require_client_auth=True
            )
        else:
            server_credentials = grpc.ssl_server_credentials(
                ((private_key, certificate_chain),)
            )

        server.add_secure_port(listen_addr, server_credentials)
        logger.info(f"🚀 gRPC Core Engine started SECURELY (TLS) on {listen_addr}")
    else:
        logger.warning("🚨 [SECURITY WARNING] gRPC running INSECURE — do NOT deploy to production")
        server.add_insecure_port(listen_addr)
        logger.info(f"🚀 gRPC Core Engine started on {listen_addr}")
    
    logger.info("⚙️ Upstream MCP Servers are initialized by startup()...")

    await server.start()
    await server.wait_for_termination()

if __name__ == '__main__':
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(serve())
