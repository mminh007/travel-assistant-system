# app/api/routes/chat.py
from app.services.background_tasks.rabbitmq_publisher import publish_extraction_task
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage
import app.core.logger as logger
from app.bootstrap.container import container
from app.graph.workflow import agent_graph
from langgraph.checkpoint.redis.aio import AsyncRedisSaver
from app.core.settings import settings
# Import Langfuse and LangSmith tracing utilities
from langfuse.langchain import CallbackHandler
from langchain_core.tracers import LangChainTracer
from app.core.metrics import SSE_ACTIVE_STREAMS, SSE_DISCONNECT_TOTAL
from app.services.streaming.chat_stream_service import ChatStreamService
from app.api.auth import get_authenticated_user_id

router = APIRouter(prefix="/chat", tags=["Agent Chat Ecosystem"])

from typing import Optional

class ChatRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    session_id: str = Field(min_length=1, max_length=128)
    prompt: str = Field(max_length=8000)

@router.post("/stream")
async def chat_stream_endpoint(
    request: ChatRequest,
    background_tasks: BackgroundTasks,
    authenticated_user_id: str = Depends(get_authenticated_user_id)
):
    if request.user_id != authenticated_user_id:
        raise HTTPException(status_code=403, detail="Forbidden: user_id mismatch")
    # Check semantic cache inside Vector DB to bypass LLM if hit
    cached_reply = await container.semantic_cache.get(request.prompt)
    if cached_reply:
        async def cached_generator():
            yield f"data: {cached_reply}\n\n"
        return StreamingResponse(cached_generator(), media_type="text/event-stream")
    
    # 🚀 OPTIMIZATION 1: Pass session_id and user_id directly to Langfuse
    # Moved to ChatStreamService


    SSE_ACTIVE_STREAMS.inc()

    async def event_generator():
        stream_completed_cleanly = False
        chat_service = ChatStreamService(bg_tasks=set())
        
        try:
            async for event_type, data in chat_service.stream(
                user_id=request.user_id,
                session_id=request.session_id,
                prompt=request.prompt,
                source="http"
            ):
                if event_type == "chunk":
                    yield f"data: {data}\n\n"
                elif event_type == "receipt":
                    import json
                    yield f"data: {json.dumps(data)}\n\n"
                elif event_type == "error":
                    yield f"data: [ERROR] {data}\n\n"

            stream_completed_cleanly = True    
        finally:
            # 🚀 METRIC: Decrement active streams and evaluate connection termination health
            SSE_ACTIVE_STREAMS.dec()
            if stream_completed_cleanly:
                SSE_DISCONNECT_TOTAL.labels(reason="completed").inc()
            else:
                SSE_DISCONNECT_TOTAL.labels(reason="abrupt_client_disconnect").inc()

    return StreamingResponse(event_generator(), media_type="text/event-stream")