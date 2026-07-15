import pytest
from app.graph.workflow import route_from_guardrail, evaluate_tool_hooks, route_from_evaluator
from langchain_core.messages import AIMessage

def test_route_from_guardrail():
    # out of domain
    assert route_from_guardrail({"is_in_domain": False}) == "out_of_domain"
    
    # confidence < 0.70
    assert route_from_guardrail({"is_in_domain": True, "intent_confidence": 0.6}) == "clarification_agent"
    
    # FAQ intent
    assert route_from_guardrail({
        "is_in_domain": True,
        "intent_confidence": 0.9,
        "intent_category": "system_navigation_faq"
    }) == "support_agent"
    
    # low complexity
    assert route_from_guardrail({
        "is_in_domain": True,
        "intent_confidence": 0.9,
        "complexity": "low"
    }) == "direct_executor_init"
    
    # medium/high complexity
    assert route_from_guardrail({
        "is_in_domain": True,
        "intent_confidence": 0.9,
        "complexity": "medium"
    }) == "planner"

def test_evaluate_tool_hooks():
    # No tool calls
    assert evaluate_tool_hooks({
        "messages": [AIMessage(content="done")]
    }) == "finding_extractor"
    
    # Iteration limit
    class MockMsg:
        tool_calls = [{"name": "test_tool", "args": {}}]
    
    assert evaluate_tool_hooks({
        "messages": [MockMsg()],
        "iteration_count": 8
    }) == "finding_extractor"
    
    # Duplicate tool call
    from app.graph.workflow import generate_tool_hash
    thash = generate_tool_hash("test_tool", {})
    assert evaluate_tool_hooks({
        "messages": [MockMsg()],
        "iteration_count": 1,
        "action_history": [thash]
    }) == "finding_extractor"
    
    # Fresh tool call
    assert evaluate_tool_hooks({
        "messages": [MockMsg()],
        "iteration_count": 1,
        "action_history": []
    }) == "execute_tools"

def test_route_from_evaluator():
    assert route_from_evaluator({"needs_rework": True, "rework_count": 0}) == "travel_react_agent"
    assert route_from_evaluator({"needs_rework": True, "rework_count": 2}) == "task_manager"
    assert route_from_evaluator({"needs_rework": False}) == "task_manager"
