"""Compiled LangGraph StateGraph for TASK-006."""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from agent.context import AgentRuntimeContext
from agent.nodes import (
    classify_intent_node,
    execute_tool_node,
    general_answer_node,
    knowledge_answer_node,
    load_conversation,
    plan_tool_node,
    plan_workflow_node,
    retrieve_knowledge_node,
    route_tool_name,
    router_node,
    save_conversation_node,
    tool_answer_node,
    unsupported_action_node,
    validate_output_node,
)
from agent.observability.instrumentation import instrument_node
from agent.routing import node_for_route
from agent.state import AgentState


def build_agent_graph():
    """Build the graph once; per-request values arrive through context."""
    builder = StateGraph(AgentState, context_schema=AgentRuntimeContext)
    builder.add_node(
        "load_conversation",
        instrument_node("load_conversation", load_conversation),
    )
    builder.add_node(
        "classify_intent",
        instrument_node("classify_intent", classify_intent_node),
    )
    builder.add_node(
        "router",
        instrument_node("router", router_node),
    )
    builder.add_node(
        "general_answer",
        instrument_node("general_answer", general_answer_node),
    )
    builder.add_node(
        "retrieve_knowledge",
        instrument_node("retrieve_knowledge", retrieve_knowledge_node),
    )
    builder.add_node(
        "knowledge_answer",
        instrument_node("knowledge_answer", knowledge_answer_node),
    )
    builder.add_node(
        "unsupported_action",
        instrument_node("unsupported_action", unsupported_action_node),
    )
    builder.add_node(
        "plan_tool",
        instrument_node("plan_tool", plan_tool_node),
    )
    builder.add_node(
        "plan_workflow",
        instrument_node("plan_workflow", plan_workflow_node),
    )
    builder.add_node(
        "execute_tool",
        instrument_node("execute_tool", execute_tool_node),
    )
    builder.add_node(
        "tool_answer",
        instrument_node("tool_answer", tool_answer_node),
    )
    builder.add_node(
        "validate_output",
        instrument_node("validate_output", validate_output_node),
    )
    builder.add_node(
        "save_conversation",
        instrument_node("save_conversation", save_conversation_node),
    )

    builder.add_edge(START, "load_conversation")
    builder.add_edge("load_conversation", "classify_intent")
    builder.add_edge("classify_intent", "router")
    builder.add_conditional_edges(
        "router",
        node_for_route,
        {
            "general_answer": "general_answer",
            "retrieve_knowledge": "retrieve_knowledge",
            "plan_tool": "plan_tool",
            "plan_workflow": "plan_workflow",
            "unsupported_action": "unsupported_action",
        },
    )
    builder.add_edge("general_answer", "validate_output")
    builder.add_edge("retrieve_knowledge", "knowledge_answer")
    builder.add_edge("knowledge_answer", "validate_output")
    builder.add_edge("unsupported_action", "validate_output")
    builder.add_conditional_edges(
        "plan_tool",
        route_tool_name,
        {
            "execute_tool": "execute_tool",
            "validate_output": "validate_output",
        },
    )
    builder.add_conditional_edges(
        "plan_workflow",
        route_tool_name,
        {
            "execute_tool": "execute_tool",
            "validate_output": "validate_output",
        },
    )
    builder.add_edge("execute_tool", "tool_answer")
    builder.add_edge("tool_answer", "validate_output")
    builder.add_edge("validate_output", "save_conversation")
    builder.add_edge("save_conversation", END)
    return builder.compile()


COMPILED_AGENT_GRAPH = build_agent_graph()
