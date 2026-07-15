# app/bootstrap/startup.py
from app.bootstrap.container import container
from app.graph import workflow
from app.mcp.mcp_client import mcp_manager

async def startup():
    await container.initialize()
    await mcp_manager.initialize_all_servers()
    workflow.agent_graph = workflow.build_workflow(mcp_manager.langchain_tools)

async def shutdown():
    await container.shutdown()