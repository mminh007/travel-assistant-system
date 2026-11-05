# app/graph/nodes/__init__.py
"""
nodes/ package — public API surface for all LangGraph node functions.

Import path (unchanged from old nodes.py):
    from app.graph.nodes import node_xxx

Module layout:
    guardrail.py        → node_input_guardrail
    planner.py          → node_planner_agent, node_direct_executor_init
    executor.py         → node_travel_react_agent, node_support_agent,
                          node_clarification_agent
    extractor.py        → node_finding_extractor
    evaluator.py        → node_fact_checker, node_evaluator_agent
                          (async shadow eval only — NOT registered in graph)
    output_guardrail.py → node_output_guardrail  (online hot-path guard)
    synthesizer.py      → node_final_synthesizer, node_task_manager
"""
from app.graph.nodes.guardrail   import node_input_guardrail
from app.graph.nodes.planner     import node_planner_agent, node_direct_executor_init
from app.graph.nodes.executor    import (
    node_travel_react_agent,
    node_support_agent,
    node_clarification_agent,
)
from app.graph.nodes.extractor         import node_finding_extractor
from app.graph.nodes.output_guardrail  import node_output_guardrail
from app.graph.nodes.synthesizer       import node_final_synthesizer, node_task_manager

# node_fact_checker and node_evaluator_agent are intentionally NOT exported here.
# They are called directly by shadow_eval_worker as plain async functions,
# not registered as LangGraph nodes in the synchronous hot-path graph.

__all__ = [
    "node_input_guardrail",
    "node_planner_agent",
    "node_direct_executor_init",
    "node_travel_react_agent",
    "node_support_agent",
    "node_clarification_agent",
    "node_finding_extractor",
    "node_output_guardrail",
    "node_final_synthesizer",
    "node_task_manager",
]
