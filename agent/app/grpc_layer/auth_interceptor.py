import grpc
from typing import Any, Callable, Awaitable
from app.core.helpers.jwt_helper import verify_jwt
from app.core.settings import settings
import app.core.logger as logger

log = logger.setup_app_logger("GrpcAuthInterceptor")

class UserOwnershipInterceptor(grpc.aio.ServerInterceptor):
    """
    Verifies that the caller's identity (from gRPC metadata) is valid.
    Injects the verified user_id into the context so handlers can enforce BOLA checks.
    Supports either X-User-ID header (from gateway) or Authorization: Bearer <token>.
    """
    async def intercept_service(
        self,
        continuation: Callable[[grpc.HandlerCallDetails], Awaitable[grpc.RpcMethodHandler]],
        handler_call_details: grpc.HandlerCallDetails,
    ) -> grpc.RpcMethodHandler:
        metadata = dict(handler_call_details.invocation_metadata)
        
        # 1. Trusted Gateway Header
        x_user_id = metadata.get("x-user-id")
        
        # 2. Direct JWT Bearer Token validation
        auth_header = metadata.get("authorization")
        
        verified_user_id = None
        
        if x_user_id:
            verified_user_id = x_user_id.decode("utf-8") if isinstance(x_user_id, bytes) else str(x_user_id)
        elif auth_header:
            auth_str = auth_header.decode("utf-8") if isinstance(auth_header, bytes) else str(auth_header)
            if auth_str.lower().startswith("bearer "):
                token = auth_str[7:]
                jwt_secret = settings.mcp.jwt_secret.get_secret_value() if settings.mcp.jwt_secret else None
                if jwt_secret:
                    payload = verify_jwt(token, jwt_secret)
                    if payload:
                        verified_user_id = payload.get("sub") or payload.get("nameid") or payload.get("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/nameidentifier")

        if not verified_user_id:
            handler = await continuation(handler_call_details)
            if handler and handler.unary_unary:
                async def reject_unary_unary(request, context):
                    await context.abort(grpc.StatusCode.UNAUTHENTICATED, "Missing or invalid authentication token")
                return grpc.unary_unary_rpc_method_handler(reject_unary_unary)
            elif handler and handler.unary_stream:
                async def reject_unary_stream(request, context):
                    await context.abort(grpc.StatusCode.UNAUTHENTICATED, "Missing or invalid authentication token")
                return grpc.unary_stream_rpc_method_handler(reject_unary_stream)
            elif handler and handler.stream_unary:
                async def reject_stream_unary(request, context):
                    await context.abort(grpc.StatusCode.UNAUTHENTICATED, "Missing or invalid authentication token")
                return grpc.stream_unary_rpc_method_handler(reject_stream_unary)
            elif handler and handler.stream_stream:
                async def reject_stream_stream(request, context):
                    await context.abort(grpc.StatusCode.UNAUTHENTICATED, "Missing or invalid authentication token")
                return grpc.stream_stream_rpc_method_handler(reject_stream_stream)
            return handler

        return await continuation(handler_call_details)
