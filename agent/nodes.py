"""Agent LangGraph 的节点实现.

文件职责:
- 每个函数对应 Graph 的一个节点.
- 读取 State 和 RuntimeContext, 返回局部 State 更新.
- 不直接访问数据库, 业务操作统一通过 Tool 和 Business Service.

核心流程:
load_conversation -> classify_intent -> router
-> general / RAG / Tool / Workflow / unsupported
-> validate_output -> save_conversation.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime
from uuid import UUID

from langgraph.runtime import Runtime

from agent.context import AgentRuntimeContext
from agent.conversation import Conversation
from agent.guardrails import (
    select_context,
    sources_from_items,
)
from agent.llm import ConversationMessage, LLMResult, ToolAwareResult
from agent.observability.instrumentation import route_for_intent
from agent.prompts import (
    GENERAL_SYSTEM_PROMPT,
    KNOWLEDGE_SYSTEM_PROMPT,
    KNOWLEDGE_USER_TEMPLATE,
    NO_KNOWLEDGE_ANSWER,
    TOOL_ANSWER_SYSTEM_PROMPT,
    TOOL_SYSTEM_PROMPT,
    UNSUPPORTED_ACTION_ANSWER,
    WORKFLOW_SYSTEM_PROMPT,
)
from agent.rag_evidence import evaluate_rag_evidence
from agent.routing import classify_intent, route_name_for_intent
from agent.safety import SafetyPipeline
from agent.state import AgentState, HistoryMessage, TokenUsage
from agent.tools.context import ToolContext


def _token_usage(result: LLMResult | ToolAwareResult) -> TokenUsage:
    """把 LLM 返回的 Token 字段转换成 AgentState 使用的 TokenUsage."""
    return TokenUsage(
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        total_tokens=result.total_tokens,
    )


async def load_conversation(
    state: AgentState,
    runtime: Runtime[AgentRuntimeContext],
) -> dict[str, object]:
    """从 Redis 读取会话历史, 新会话则创建空历史."""
    context = runtime.context
    conversation = await context.conversation_store.load(
        user_id=context.user.id,
        conversation_id=UUID(state["conversation_id"]),
        create=context.is_new_conversation,
    )
    return {
        "history": conversation.messages,
        "conversation_created_at": conversation.created_at.isoformat(),
    }


async def classify_intent_node(
    state: AgentState,
    runtime: Runtime[AgentRuntimeContext],
) -> dict[str, object]:
    """调用确定性规则和 LLM 识别用户意图."""
    intent = await classify_intent(
        llm=runtime.context.llm,
        message=state["user_message"],
    )
    trace = runtime.context.trace
    if trace is not None:
        risk = (
            "MEDIUM"
            if intent in {"WORKFLOW", "UNSUPPORTED_ACTION"}
            else "LOW"
        )
        trace.emit(
            "route_decision",
            node_name="classify_intent",
            intent=intent,
            route=route_for_intent(intent),
            risk_level=risk,
            execution_status="SUCCESS",
            result_summary={"intent": intent},
        )
    return {"intent": intent}


async def router_node(
    state: AgentState,
    runtime: Runtime[AgentRuntimeContext],
) -> dict[str, object]:
    """把 Intent 规范化为显式 route, 并记录当前用户角色."""
    context = runtime.context
    # Router 只规范化 route 和 user_role; 具体业务动作由后续节点执行.
    route = state.get("route") or route_name_for_intent(state.get("intent"))
    user_role = "admin" if context.user.is_admin else "user"
    trace = context.trace
    if trace is not None:
        trace.emit(
            "router_decision",
            node_name="router",
            intent=state.get("intent"),
            route=route.upper(),
            execution_status="SUCCESS",
            result_summary={"route": route, "user_role": user_role},
        )
    return {"route": route, "user_role": user_role}


async def general_answer_node(
    state: AgentState,
    runtime: Runtime[AgentRuntimeContext],
) -> dict[str, object]:
    """处理不依赖知识库或业务工具的普通对话."""
    context = runtime.context
    selection = select_context(
        history=state.get("history", []),
        user_message=state["user_message"],
        rag_items=[],
        settings=context.settings,
    )
    result = await context.llm.generate(
        system_prompt=GENERAL_SYSTEM_PROMPT,
        messages=[
            ConversationMessage(role=message.role, content=message.content)
            for message in selection.history
        ],
        user_message=state["user_message"],
    )
    return {
        "answer": result.text,
        "sources": [],
        "token_usage": _token_usage(result),
    }


async def retrieve_knowledge_node(
    state: AgentState,
    runtime: Runtime[AgentRuntimeContext],
) -> dict[str, object]:
    """检索知识 Chunk, 并在进入回答前做证据充分性判断."""
    context = runtime.context
    retrieval = context.retrieval
    retrieval_reason: str | None = None
    if hasattr(retrieval, "retrieve_with_diagnostics"):
        outcome = await retrieval.retrieve_with_diagnostics(
            user=context.user,
            query=state["user_message"],
            top_k=context.settings.agent_rag_top_k,
        )
        items = outcome.items
        retrieval_reason = outcome.reason
    else:
        # Test doubles and older boundary implementations remain supported.
        items = await retrieval.retrieve(
            user=context.user,
            query=state["user_message"],
            top_k=context.settings.agent_rag_top_k,
        )
        retrieval_reason = "OK" if items else "NO_CANDIDATES"

    # 检索结果先做证据判定, 不满足阈值时不会进入回答节点.
    decision = evaluate_rag_evidence(
        query=state["user_message"],
        items=items,
        settings=context.settings,
        retrieval_reason=retrieval_reason,
    )
    trace = context.trace
    if trace is not None:
        trace.emit(
            "rag_retrieval",
            node_name="retrieve_knowledge",
            intent="RAG",
            route="RAG",
            risk_level="LOW",
            execution_status=(
                "SUCCESS"
                if decision.answerable
                else "EMPTY" if not items else "REJECTED"
            ),
            result_summary={
                "retrieved_count": len(items),
                "top_score": items[0].score if items else None,
                "retrieval_reason": retrieval_reason,
                "decision_reason": decision.reason,
                "evidence_coverage": decision.evidence_coverage,
            },
        )
        trace.emit(
            "rag_decision",
            node_name="retrieve_knowledge",
            intent="RAG",
            route="RAG",
            risk_level="LOW",
            execution_status="SUCCESS",
            result_summary={
                "answerable": decision.answerable,
                "reason": decision.reason,
                "top_score": decision.top_score,
                "evidence_coverage": decision.evidence_coverage,
                "min_score": decision.min_score,
                "high_confidence_score": decision.high_confidence_score,
                "min_evidence_coverage": decision.min_evidence_coverage,
            },
        )
    return {
        "retrieved_items": items if decision.answerable else [],
    }


async def knowledge_answer_node(
    state: AgentState,
    runtime: Runtime[AgentRuntimeContext],
) -> dict[str, object]:
    """只根据已通过证据判断的 RAG 片段生成回答和来源."""
    context = runtime.context
    items = state.get("retrieved_items", [])
    selection = select_context(
        history=state.get("history", []),
        user_message=state["user_message"],
        rag_items=items,
        settings=context.settings,
    )
    if not selection.rag_items:
        return {
            "answer": NO_KNOWLEDGE_ANSWER,
            "sources": [],
            "token_usage": TokenUsage(),
        }

    result = await context.llm.generate(
        system_prompt=KNOWLEDGE_SYSTEM_PROMPT,
        messages=[
            ConversationMessage(role=message.role, content=message.content)
            for message in selection.history
        ],
        user_message=KNOWLEDGE_USER_TEMPLATE.format(
            question=state["user_message"],
            context_json=selection.context_text,
        ),
    )
    return {
        "answer": result.text,
        "sources": sources_from_items(selection.rag_items),
        "token_usage": _token_usage(result),
    }


async def unsupported_action_node(
    state: AgentState,
    runtime: Runtime[AgentRuntimeContext],
) -> dict[str, object]:
    """对不支持的写操作返回固定说明, 不调用模型和业务工具."""
    return {
        "answer": UNSUPPORTED_ACTION_ANSWER,
        "sources": [],
        "token_usage": TokenUsage(),
    }


async def validate_output_node(
    state: AgentState,
    runtime: Runtime[AgentRuntimeContext],
) -> dict[str, object]:
    """统一执行输出安全检查, 防止敏感信息和非法 Source."""
    context = runtime.context
    answer = SafetyPipeline(context.settings).validate_output(
        state.get("answer", ""),
        sources=state.get("sources", []),
        retrieved_items=state.get("retrieved_items", []),
    )
    trace = context.trace
    if trace is not None:
        trace.emit(
            "output_validation",
            node_name="validate_output",
            intent=state.get("intent"),
            route=route_for_intent(state.get("intent")),
            execution_status="SUCCESS",
            result_summary={"answer_length": len(answer)},
        )
    return {"answer": answer}


async def save_conversation_node(
    state: AgentState,
    runtime: Runtime[AgentRuntimeContext],
) -> dict[str, object]:
    """在持有会话锁的前提下保存本轮用户和助手消息."""
    context = runtime.context
    created_at_raw = state.get("conversation_created_at")
    created_at = (
        datetime.fromisoformat(created_at_raw)
        if created_at_raw
        else datetime.now(UTC)
    )
    messages = [
        *state.get("history", []),
        HistoryMessage(role="user", content=state["user_message"]),
        HistoryMessage(role="assistant", content=state["answer"]),
    ]
    conversation = Conversation(
        conversation_id=UUID(state["conversation_id"]),
        user_id=context.user.id,
        messages=messages,
        created_at=created_at,
        updated_at=datetime.now(UTC),
    )
    await context.conversation_store.require_lock_for_save(
        conversation=conversation,
        token=context.lock_token,
    )
    trace = context.trace
    if trace is not None:
        trace.emit(
            "conversation_saved",
            node_name="save_conversation",
            intent=state.get("intent"),
            route=route_for_intent(state.get("intent")),
            execution_status="SUCCESS",
            result_summary={"message_count": len(messages)},
        )
    return {}


async def _plan_tool(
    state: AgentState,
    runtime: Runtime[AgentRuntimeContext],
    *,
    system_prompt: str,
    kinds: frozenset[str],
    route: str,
    node_name: str,
) -> dict[str, object]:
    """让模型从指定 kind 的工具中选择至多一个.

    Args:
        system_prompt: 工具规划 Prompt.
        kinds: 允许暴露的工具类型, READ 或 PREPARE.
        route: Trace 中记录的 route 标签.
        node_name: 当前节点名.

    Returns:
        包含 tool_name 和 tool_args 的局部 State; 没有工具时直接返回回答.
    """
    context = runtime.context
    executor = context.tool_executor
    if executor is None:
        raise RuntimeError("Tool executor is not configured")

    # 规划阶段只选择一个工具, 工具名和参数由 Registry 与 Pydantic 校验.
    result = await context.llm.generate_with_tools(
        system_prompt=system_prompt,
        messages=[
            ConversationMessage(role=message.role, content=message.content)
            for message in state.get("history", [])
        ],
        user_message=state["user_message"],
        tools=executor.registry.openai_tools(kinds=kinds),
        max_output_tokens=256,
    )
    trace = context.trace
    if trace is not None:
        trace.emit(
            "tool_plan",
            node_name=node_name,
            intent=state.get("intent"),
            route=route,
            execution_status="SUCCESS",
            result_summary={
                "tool_call_count": len(result.tool_calls),
                "tool_names": [call.name for call in result.tool_calls],
            },
        )
    if not result.tool_calls:
        # 没有工具调用说明模型无法从当前消息中得到明确业务对象, 直接返回提示.
        return {
            "answer": result.text or "请补充要查询或操作的具体业务编号。",
            "sources": [],
            "tool_call_count": 1,
            "token_usage": _token_usage(result),
        }

    selected = result.tool_calls[0]
    return {
        "tool_name": selected.name,
        "tool_args": selected.args,
        "tool_call_count": 1,
        "token_usage": _token_usage(result),
    }


async def plan_tool_node(
    state: AgentState,
    runtime: Runtime[AgentRuntimeContext],
) -> dict[str, object]:
    """只向规划器暴露 READ 工具."""
    return await _plan_tool(
        state,
        runtime,
        system_prompt=TOOL_SYSTEM_PROMPT,
        kinds=frozenset({"READ"}),
        route="TOOL",
        node_name="plan_tool",
    )


async def plan_workflow_node(
    state: AgentState,
    runtime: Runtime[AgentRuntimeContext],
) -> dict[str, object]:
    """只向规划器暴露 PREPARE 工具, 生成待确认或待审批计划."""
    return await _plan_tool(
        state,
        runtime,
        system_prompt=WORKFLOW_SYSTEM_PROMPT,
        kinds=frozenset({"PREPARE"}),
        route="WORKFLOW",
        node_name="plan_workflow",
    )


def _confirmation_store(context: AgentRuntimeContext):
    """读取用户确认存储, 缺失时直接暴露配置错误."""
    store = context.confirmation_store
    if store is None:
        raise RuntimeError("Confirmation store is not configured")
    return store


async def execute_tool_node(
    state: AgentState,
    runtime: Runtime[AgentRuntimeContext],
) -> dict[str, object]:
    """执行规划阶段选中的 Tool, 并把结果写回 State.

    这是 Agent 产生业务副作用的唯一节点入口; Tool 内部仍必须经过 Service.
    """
    context = runtime.context
    executor = context.tool_executor
    if executor is None:
        raise RuntimeError("Tool executor is not configured")
    tool_name = state.get("tool_name")
    if not tool_name:
        raise RuntimeError("Tool name is missing")

    # 这里才真正执行 Tool; 写操作仍由 Tool 调用 Business Service.
    result = await executor.execute(
        tool_name,
        state.get("tool_args", {}),
        ToolContext(
            user=context.user,
            session=context.session,
            settings=context.settings,
            conversation_id=UUID(state["conversation_id"]),
            confirmation_store=_confirmation_store(context),
            trace=context.trace,
            route=route_for_intent(state.get("intent")),
        ),
    )
    return {
        "tool_result": asdict(result),
        "pending_action": result.pending_action,
        "approval_required": bool(
            result.pending_action
            and result.pending_action.get("approval_required")
        ),
        "approval_id": (
            result.pending_action.get("approval_id")
            if result.pending_action
            else None
        ),
        "approval_status": (
            result.pending_action.get("approval_status")
            if result.pending_action
            else None
        ),
        "tool_call_count": state.get("tool_call_count", 0) + 1,
    }


async def tool_answer_node(
    state: AgentState,
    runtime: Runtime[AgentRuntimeContext],
) -> dict[str, object]:
    """把 ToolResult 转换成面向用户的回答.

    pending action 直接返回待确认/待审批说明; 成功结果再交给模型总结.
    """
    result = state.get("tool_result") or {}
    pending_action = state.get("pending_action")
    # 管理员审批与用户确认是两条不同路径; 这里只返回对应的 pending 状态.
    if pending_action:
        if pending_action.get("approval_required"):
            return {
                "answer": (
                    "已创建库存调整审批，等待管理员在审批中心处理："
                    f"approval_id={pending_action.get('approval_id')}。"
                    "审批通过前不会修改库存。"
                ),
                "sources": [],
            }
        return {
            "answer": (
                "已准备该业务操作，请通过独立确认接口确认后执行："
                f"confirmation_id={pending_action.get('confirmation_id')}。"
            ),
            "sources": [],
        }
    if not result.get("ok"):
        code = result.get("error_code") or "AGENT_TOOL_EXECUTION_FAILED"
        message = result.get("error_message") or "业务操作未完成"
        return {
            "answer": f"业务工具执行失败（{code}）：{message}",
            "sources": [],
        }

    context = runtime.context
    # 把结构化 Tool 结果交给模型总结, 不允许模型补造缺失字段.
    answer_result = await context.llm.generate(
        system_prompt=TOOL_ANSWER_SYSTEM_PROMPT,
        messages=[],
        user_message=json.dumps(
            {"tool": state.get("tool_name"), "result": result.get("data")},
            ensure_ascii=False,
        ),
    )
    previous = state.get("token_usage", TokenUsage())
    return {
        "answer": answer_result.text,
        "sources": [],
        "token_usage": previous.plus(_token_usage(answer_result)),
    }


def route_tool_name(state: AgentState) -> str:
    """有选中工具时执行, 否则直接进入输出校验."""
    return "execute_tool" if state.get("tool_name") else "validate_output"

