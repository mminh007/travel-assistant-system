# app/graph/workflow.py
import os
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
#from langgraph.checkpoint.redis.aio import AsyncRedisSaver
#import redis
import hashlib
from app.graph.state import AgentState
from app.graph.nodes import (
    node_input_guardrail, 
    node_travel_react_agent,
    node_planner_agent,
    node_direct_executor_init,
    node_critic_agent,
    node_final_synthesizer,
    node_reflection_agent,
    node_task_manager,
    node_finding_extractor,
)
from langchain_core.messages import AIMessage
from langchain_core.messages import HumanMessage
from app.mcp.mcp_client import get_mcp_tools
from app.core.logger import setup_app_logger
from app.core.metrics import FORCED_TERMINATION_TOTAL, DUPLICATE_TOOL_CALL_TOTAL, GRAPH_ITERATIONS

logger = setup_app_logger("WorkflowOrchestrator")

# Initialize and configure the central tool interface
mcp_tools = get_mcp_tools()
tool_node = ToolNode(mcp_tools)
workflow = StateGraph(AgentState)

# Register the Master Router along with all domain-isolated specialist nodes
# We add a simple node for out of domain responses
async def node_out_of_domain(state):
    return {"messages": [AIMessage(content="I am a Travel AI Assistant. I can only help with hotel bookings, flight bookings, itineraries, and travel recommendations.")]}

workflow.add_node("input_guardrail", node_input_guardrail)
workflow.add_node("out_of_domain", node_out_of_domain)
workflow.add_node("travel_react_agent", node_travel_react_agent)
workflow.add_node("planner", node_planner_agent)
workflow.add_node("direct_executor_init", node_direct_executor_init)
workflow.add_node("critic_agent", node_critic_agent)
workflow.add_node("reflection_agent", node_reflection_agent)
workflow.add_node("task_manager", node_task_manager)
workflow.add_node("finding_extractor", node_finding_extractor)
workflow.add_node("final_synthesizer", node_final_synthesizer)

workflow.set_entry_point("input_guardrail")

# ─── PHASE 1: COMPLEXITY-AWARE ROUTING ───
def route_from_guardrail(state: AgentState) -> str:
    """Routes out of domain or to planner/direct init."""
    if not state.get("is_in_domain", True):
        return "out_of_domain"
    
    complexity = state.get("complexity", "medium")
    if complexity == "low":
        return "direct_executor_init"
    return "planner"

workflow.add_conditional_edges(
    "input_guardrail",
    route_from_guardrail,
    {
        "out_of_domain": "out_of_domain",
        "direct_executor_init": "direct_executor_init",
        "planner": "planner"
    }
)

workflow.add_edge("out_of_domain", END)

workflow.add_edge("planner", "travel_react_agent")
workflow.add_edge("direct_executor_init", "travel_react_agent")

# ─── PHASE 2: CONFIGURABLE HARD LIMITS ───
MAX_ITERATIONS   = 8    # Prevent infinite Thought/Action loops within a single task
MAX_TOOL_CALLS   = 10   # Prevent budget drain across the execution lifecycle
MAX_REWORK_CYCLES = 2   # Cap Critic→Reflection→Executor rework loops per task

def generate_tool_hash(tool_name: str, args: dict) -> str:
    """Creates a unique deterministic hash for a tool call to detect exact duplicates."""
    raw_str = f"{tool_name}_{str(sorted(args.items()))}"
    return hashlib.md5(raw_str.encode()).hexdigest()

def evaluate_tool_hooks(state: AgentState) -> str:
    """
    Detects active tool calls while enforcing strict programmatic safeguards:
    Max Iterations, Budget Limits, and Duplicate Detection.

    REFACTORED: Removed the fragile JSON confidence check that parsed executor
    output as ExecutorOutput JSON. Executor nodes now return plain Markdown;
    structured extraction is handled by node_finding_extractor. When no tool
    calls are detected, routes to 'finding_extractor' (not 'critic_agent' directly).
    """
    last_message = state["messages"][-1]
    session_id = state.get("session_id", "UNKNOWN_SESSION")
    domain = "travel_react_agent"
    
    if not hasattr(last_message, "tool_calls") or not last_message.tool_calls:
        # Executor is done — route to finding extractor before critic evaluation
        return "finding_extractor"

    # 1. MAX ITERATION & BUDGET SAFEGUARD
    if state.get("iteration_count", 0) >= MAX_ITERATIONS:
        logger.warning(f"🛑 [Safeguard Tripped] Session {session_id}: Max loops reached. Forcing termination.\n")
        FORCED_TERMINATION_TOTAL.labels(domain=domain, reason="max_iterations").inc()
        return "finding_extractor"  # Force extraction before critic
    
    if state.get("tool_call_count", 0) >= MAX_TOOL_CALLS:
        logger.warning(f"🛑 [Safeguard Tripped] Session {session_id}: Max tools budget reached. Forcing termination.\n")
        FORCED_TERMINATION_TOTAL.labels(domain=domain, reason="budget_depleted").inc()
        return "finding_extractor"

    action_history = state.get("action_history", [])
    
    # 2. DUPLICATE ACTION DETECTION
    for tool_call in last_message.tool_calls:
        t_hash = generate_tool_hash(tool_call['name'], tool_call['args'])
        if t_hash in action_history:
            logger.warning(f"🛑 [Duplicate Detection] Blocked redundant tool call: {tool_call['name']}\n")
            DUPLICATE_TOOL_CALL_TOTAL.labels(tool_name=tool_call['name']).inc()
            FORCED_TERMINATION_TOTAL.labels(domain=domain, reason="duplicate_action").inc()
            return "finding_extractor"
            
    tool_names = [t['name'] for t in last_message.tool_calls]
    logger.info(f"==> [Tool Action Dispatched] Session: {session_id} -> Executing: {tool_names}")
    return "execute_tools"


async def action_tracker_node(state: AgentState):
    """
    Interceptor node that updates workflow memory (action history & counters) 
    BEFORE executing the actual tools.
    """
    last_msg = state["messages"][-1]
    action_history = state.get("action_history", [])
    tool_call_count = state.get("tool_call_count", 0)
    
    new_hashes = []
    if hasattr(last_msg, "tool_calls"):
        for tc in last_msg.tool_calls:
            new_hashes.append(generate_tool_hash(tc['name'], tc['args']))
            tool_call_count += 1
            
    return {
        "action_history": action_history + new_hashes,
        "tool_call_count": tool_call_count
    }

workflow.add_node("action_tracker", action_tracker_node)
workflow.add_node("tools", tool_node)

# Bind tool validation endpoints across all worker components
# When executor has no more tool calls, routes to finding_extractor for structured extraction
executor_map = {"execute_tools": "action_tracker", "finding_extractor": "finding_extractor"}
workflow.add_conditional_edges("travel_react_agent", evaluate_tool_hooks, executor_map)

# Link tracker directly to the actual LangChain ToolNode
workflow.add_edge("action_tracker", "tools")

# finding_extractor always proceeds to critic_agent after extraction completes
workflow.add_edge("finding_extractor", "critic_agent")

def route_back_to_agent(state: AgentState) -> str:
    return "travel_react_agent"

workflow.add_conditional_edges(
    "tools",
    route_back_to_agent,
    {"travel_react_agent": "travel_react_agent"}
)

# ─── PHASE 3: EVALUATION & SYNTHESIS PIPELINE ───
workflow.add_edge("critic_agent", "reflection_agent")

def route_from_reflection(state: AgentState) -> str:
    if state.get("needs_rework"):
        if state.get("rework_count", 0) >= MAX_REWORK_CYCLES:
            return "task_manager"
        return "travel_react_agent"
    return "task_manager"
workflow.add_conditional_edges(
    "reflection_agent",
    route_from_reflection,
    {
        "travel_react_agent": "travel_react_agent",
        "task_manager": "task_manager"
    }
)

def route_from_task_manager(state: AgentState) -> str:
    if state.get("current_task_id") is not None:
        return "travel_react_agent"
    return "final_synthesizer"

workflow.add_conditional_edges(
    "task_manager",
    route_from_task_manager,
    {
        "travel_react_agent": "travel_react_agent",
        "final_synthesizer": "final_synthesizer"
    }
)

workflow.add_edge("final_synthesizer", END)

compiled_graph = workflow.compile(name="compiled_graph") 

