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
from app.graph.workflow import agent_graph
from langgraph.checkpoint.redis.aio import AsyncRedisSaver
from app.core.settings import settings
from app.mcp.mcp_client import mcp_manager
from app.bootstrap.startup import startup, shutdown
from app.bootstrap.container import container
from app.core.helpers.asymmetric_helper import sign_data_es256
from app.core.helpers.crypto_helper import encrypt_value, decrypt_value
from app.services.streaming.chat_stream_service import ChatStreamService

from prometheus_client import Gauge, Counter
from prometheus_client import start_http_server

logger = setup_app_logger("GrpcServerCore")

GRPC_ACTIVE_STREAMS = Gauge(
    'grpc_active_streams', 
    'Number of concurrent active gRPC chat streams currently processing'
)

GRPC_ERRORS_TOTAL = Counter(
    'grpc_errors_total', 
    'Total number of gRPC runtime pipeline exceptions caught'
)

class AgentServiceServicer(chat_pb2_grpc.AgentServiceServicer):
    def __init__(self):
        self.graph = agent_graph
        self._bg_tasks = set()

    async def UpdateProviderConfig(self, request: chat_pb2.ProviderConfigRequest, context: grpc.aio.ServicerContext):
        logger.info(f"==> [gRPC] Received config update from User: {request.user_id}")
        
        metadata = dict(context.invocation_metadata())
        verified_user_id = metadata.get("x-verified-user-id")
        
        if not verified_user_id:
            context.set_code(grpc.StatusCode.UNAUTHENTICATED)
            context.set_details("Missing authentication")
            return chat_pb2.ProviderConfigResponse(success=False, message="Unauthenticated")
            
        if verified_user_id != request.user_id:
            context.set_code(grpc.StatusCode.PERMISSION_DENIED)
            context.set_details("Forbidden: cannot modify another user's config")
            return chat_pb2.ProviderConfigResponse(success=False, message="Forbidden")
        
        if not container.redis_client:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details("Redis client not initialized.")
            return chat_pb2.ProviderConfigResponse(success=False, message="Redis not initialized.")
            
        config_dict = {"user_id": request.user_id}
        
        if request.HasField("default"):
            # User wants to use system default key for this provider
            config_dict["llm_provider"] = request.default
            config_dict["use_default_key"] = True
        elif request.HasField("llm_provider"):
            if not request.HasField("api_key"):
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details("Custom provider requires an api_key.")
                return chat_pb2.ProviderConfigResponse(success=False, message="Custom provider requires an api_key.")
            config_dict["llm_provider"] = request.llm_provider
            config_dict["api_key"] = encrypt_value(request.api_key) if request.api_key else None
            config_dict["use_default_key"] = False
        
        await container.redis_client.setex(
            f"user_config:{request.user_id}",
            86400,
            json.dumps(config_dict)
        )
        
        return chat_pb2.ProviderConfigResponse(success=True, message=f"Configuration saved for user {request.user_id}")

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
        
        # 🚀 OPTIMIZATION: Check semantic cache inside Vector DB to bypass LLM if hit
        try:
            cached_reply = await container.semantic_cache.get(request.prompt)
        except Exception as cache_err:
            logger.warning(f"==> [gRPC] Semantic cache lookup failed, treating as MISS: {cache_err}")
            cached_reply = None
        if cached_reply:
            logger.info(f"==> [gRPC] Cache hit for User: {request.user_id}")
            yield chat_pb2.ChatResponse(chunk=cached_reply)
            return
        
        # 🚀 METRIC: Increment active stream gauge
        GRPC_ACTIVE_STREAMS.inc()

        # Extract dynamic configuration from gRPC headers/metadata
        metadata = {k.lower(): v for k, v in context.invocation_metadata()}
        llm_provider = metadata.get("x-llm-provider")
        # Header renamed from x-api-key to x-llm-token to avoid proxy logging capture
        api_key = metadata.get("x-llm-token")
        base_url = metadata.get("x-base-url")
        tier1_model = metadata.get("x-tier1-model")
        tier2_model = metadata.get("x-tier2-model")
        tier3_model = metadata.get("x-tier3-model")

        # ─── FALLBACK TO DYNAMIC USER CONFIG FROM REDIS ───
        from app.services.user.user_config_service import load_user_llm_config
        user_config = await load_user_llm_config(request.user_id, container.redis_client)
        llm_provider = llm_provider or user_config.get("llm_provider")
        api_key = api_key or user_config.get("api_key")
        use_default_key = user_config.get("use_default_key", False)

        try:
            chat_service = ChatStreamService(bg_tasks=self._bg_tasks)
            async for event_type, data in chat_service.stream(
                user_id=request.user_id,
                session_id=request.session_id,
                prompt=request.prompt,
                llm_provider=llm_provider,
                api_key=api_key,
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
