# app/bootstrap/startup.py
from app.bootstrap.container import container
from app.graph import workflow
from app.mcp.mcp_client import mcp_manager
from app.bootstrap.health import ping_llm_provider, ping_redis
import logging

logger = logging.getLogger("Startup")

async def startup():
    await ping_redis()
    await ping_llm_provider()
    await container.initialize()
    tools = await mcp_manager.initialize_all_servers()
    if not tools:
        logger.warning("⚠️ [Startup] No MCP tools loaded — agent will run in tool-free mode")
    workflow.agent_graph = workflow.build_workflow(tools)

async def shutdown():
    await container.shutdown()