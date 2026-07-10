# app/mcp/tool_registry.py
from typing import List
from langchain_core.tools import BaseTool
from app.mcp.mcp_client import get_mcp_tools

# Define tool boundaries for each agent domain.
# When the system grows to 100+ tools, only this registry needs to be updated.
AGENT_TOOL_REGISTRY = {
    "travel": [
        "search_web",
        "search_hotel_database"
    ],
    "support": [
        "search_hotel_database"
    ]
}

def get_tools_by_domain(domain: str) -> List[BaseTool]:
    """
    Optimized O(1) tool lookup path. Resolves registered tools for a given 
    domain against the master list of cached MCP tools.
    
    This fulfills the exact import signature required by app/graph/nodes.py.
    """
    # Fetch the master pre-loaded tools list from the client manager cache
    all_mcp_tools = get_mcp_tools()
    
    # Import local tools and combine them
    from app.mcp.local_tools import LOCAL_TOOLS
    combined_tools = all_mcp_tools + LOCAL_TOOLS
    
    allowed_tool_names = AGENT_TOOL_REGISTRY.get(domain, [])

    # Map names directly to base tool schemas
    return [
        tool for tool in combined_tools
        if tool.name in allowed_tool_names
    ]

