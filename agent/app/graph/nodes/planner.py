# app/graph/nodes/planner.py
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.runnables import RunnableConfig

from app.graph.state import AgentState
from app.graph.config import get_structured_llm, invoke_llm_with_limit
from app.graph.schemas import PlannerOutput
from app.graph.utils import update_token_usage
from app.core.settings import settings
from app.core.logger import setup_app_logger

logger = setup_app_logger("CognitiveNodes")


async def node_planner_agent(state: AgentState, config: RunnableConfig = None):
    """
    Node: PLANNER_AGENT.
    Acts as the project manager. Takes a complex travel query, evaluates feasibility,
    and breaks it down into a linear execution plan stored in Workflow Memory.
    """
    user_initial_prompt = state["messages"][-1].content if state["messages"] else ""
    objective = state.get("objective", user_initial_prompt)
    logger.info(f"==> [Planner] Breaking down travel request: '{user_initial_prompt[:50]}...'")

    try:
        structured_planner_llm = get_structured_llm(2, PlannerOutput, config)
        plan, usage = await invoke_llm_with_limit(2, structured_planner_llm, [
            SystemMessage(
                content=(
                    "You are the Travel Master Planner. Break down the user's travel request into 2-4 "
                    "concrete, sequential sub-tasks. Focus on logical progression.\n\n"
                    f"Overarching Objective: {objective}\n"
                    "CRITICAL ROUTING RULES:\n"
                    "- Only output logical travel tasks like 'Search for hotel', 'Check availability', etc.\n"
                    f"- Write all task descriptions strictly in the user's language: {state.get('detected_language', 'Vietnamese')}. Never use Chinese."
                )
            ),
            HumanMessage(content=user_initial_prompt)
        ], config, max_tokens_override=settings.node_limits.planner_agent, node_name="planner_agent")

        tasks_state = [
            {"id": t.id, "desc": t.description, "status": "pending", "result": None, "findings": []}
            for t in plan.tasks
        ]
        logger.info(f"==> [Planner] Generated {len(tasks_state)} tasks successfully.")
        token_update = update_token_usage(state, usage, node_name="planner_agent")

    except Exception as plan_err:
        logger.error(f"❌ [PLANNER FAILURE] Structured parse failed — falling back to single task. Trace: {str(plan_err)}")
        tasks_state = [{"id": 1, "desc": user_initial_prompt, "status": "pending", "result": None, "findings": []}]
        token_update = {}

    return {
        "tasks": tasks_state,
        "current_task_id": tasks_state[0]["id"] if tasks_state else None,
        "iteration_count": 0,
        "tool_call_count": 0,
        "action_history": [],
        "rework_count": 0,
        **token_update
    }


async def node_direct_executor_init(state: AgentState):
    """
    Node: DIRECT_EXECUTOR_INIT.
    Lightweight initializer for the complexity='low' bypass path.
    Skips Planner to save LLM cost, creates a single synthetic task from the user prompt,
    and sets all required loop counters to their initial values.
    """
    user_initial_prompt = state["messages"][-1].content if state["messages"] else ""
    objective = state.get("objective", user_initial_prompt)
    tasks_state = [{"id": 1, "desc": objective, "status": "pending", "result": None, "findings": []}]

    logger.info("==> [DirectInit] Low-complexity bypass: skipping Planner, single task created.")

    return {
        "tasks": tasks_state,
        "current_task_id": 1,
        "iteration_count": 0,
        "tool_call_count": 0,
        "action_history": [],
        "rework_count": 0
    }
