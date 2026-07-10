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
            verified_user_id = x_user_id
        elif auth_header and auth_header.lower().startswith("bearer "):
            token = auth_header[7:]
            jwt_secret = settings.mcp.jwt_secret.get_secret_value() if settings.mcp.jwt_secret else None
            if jwt_secret:
                payload = verify_jwt(token, jwt_secret)
                if payload and "sub" in payload:
                    verified_user_id = payload["sub"]

        # Proceed even if unauthenticated, but append the verified_user_id to metadata
        # so individual handlers can enforce auth as needed.
        if verified_user_id:
            # We cannot easily modify handler_call_details.invocation_metadata since it's a tuple.
            # We can pass it as a custom key. But we must reconstruct the metadata tuple.
            new_metadata = list(handler_call_details.invocation_metadata)
            new_metadata.append(("x-verified-user-id", verified_user_id))
            handler_call_details = handler_call_details._replace(invocation_metadata=tuple(new_metadata))

        return await continuation(handler_call_details)
