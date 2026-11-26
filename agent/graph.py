"""Agent 主 LangGraph 的装配文件.

文件职责:
- 注册所有 Node.
- 连接普通边和条件边.
- 编译主图供 AgentRuntime 调用.

核心流程:
START -> load_conversation -> classify_intent -> router
      -> general / rag / tool / workflow / unsupported
      -> validate_output -> save_conversation -> END.

运行方式:
不直接运行本文件. 由 AgentRuntime.chat 调用 COMPILED_AGENT_GRAPH.ainvoke.
"""

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
    """装配并编译主图.

    Returns:
        编译后的 LangGraph 对象, 供 AgentRuntime 以 ainvoke 调用.
    """
    builder = StateGraph(AgentState, context_schema=AgentRuntimeContext)

    # ① 注册节点. instrument_node 透明记录节点开始, 结束和异常.
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

    # ② 固定入口和意图分类, 然后进入显式 Router.
    builder.add_edge(START, "load_conversation")
    builder.add_edge("load_conversation", "classify_intent")
    builder.add_edge("classify_intent", "router")
    # ③ Router 根据 route 选择 RAG, Tool, Workflow 或普通回答.
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
    # ④ Tool 规划可能没有选中工具, 此时直接进入输出校验.
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
    # ⑤ 所有路径最终统一做输出校验并保存会话.
    builder.add_edge("validate_output", "save_conversation")
    builder.add_edge("save_conversation", END)
    return builder.compile()


# 主图在进程启动时编译一次; 当前没有配置 checkpointer.
COMPILED_AGENT_GRAPH = build_agent_graph()
