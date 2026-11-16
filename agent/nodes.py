"""Node implementations for the TASK-006 LangGraph workflow."""

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
    validate_output,
)
from agent.llm import ConversationMessage, LLMResult, ToolAwareResult
from agent.prompts import (
    GENERAL_SYSTEM_PROMPT,
    KNOWLEDGE_SYSTEM_PROMPT,
    KNOWLEDGE_USER_TEMPLATE,
    NO_KNOWLEDGE_ANSWER,
    TOOL_ANSWER_SYSTEM_PROMPT,
    TOOL_SYSTEM_PROMPT,
    UNSUPPORTED_ACTION_ANSWER,
)
from agent.routing import classify_intent
from agent.state import AgentState, HistoryMessage, TokenUsage
from agent.tools.context import ToolContext


def _token_usage(result: LLMResult | ToolAwareResult) -> TokenUsage:
    return TokenUsage(
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        total_tokens=result.total_tokens,
    )


async def load_conversation(
    state: AgentState,
    runtime: Runtime[AgentRuntimeContext],
) -> dict[str, object]:
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
    intent = await classify_intent(
        llm=runtime.context.llm,
        message=state["user_message"],
    )
    return {"intent": intent}


async def general_answer_node(
    state: AgentState,
    runtime: Runtime[AgentRuntimeContext],
) -> dict[str, object]:
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
    context = runtime.context
    items = await context.retrieval.retrieve(
        user=context.user,
        query=state["user_message"],
        top_k=context.settings.agent_rag_top_k,
    )
    return {"retrieved_items": items}


async def knowledge_answer_node(
    state: AgentState,
    runtime: Runtime[AgentRuntimeContext],
) -> dict[str, object]:
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
    return {
        "answer": UNSUPPORTED_ACTION_ANSWER,
        "sources": [],
        "token_usage": TokenUsage(),
    }


async def validate_output_node(
    state: AgentState,
    runtime: Runtime[AgentRuntimeContext],
) -> dict[str, object]:
    answer = validate_output(
        state.get("answer", ""),
        sources=state.get("sources", []),
        retrieved_items=state.get("retrieved_items", []),
        settings=runtime.context.settings,
    )
    return {"answer": answer}


async def save_conversation_node(
    state: AgentState,
    runtime: Runtime[AgentRuntimeContext],
) -> dict[str, object]:
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
    return {}


async def plan_tool_node(
    state: AgentState,
    runtime: Runtime[AgentRuntimeContext],
) -> dict[str, object]:
    context = runtime.context
    executor = context.tool_executor
    if executor is None:
        raise RuntimeError("Tool executor is not configured")

    result = await context.llm.generate_with_tools(
        system_prompt=TOOL_SYSTEM_PROMPT,
        messages=[
            ConversationMessage(role=message.role, content=message.content)
            for message in state.get("history", [])
        ],
        user_message=state["user_message"],
        tools=executor.registry.openai_tools(),
        max_output_tokens=256,
    )
    if not result.tool_calls:
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


def _confirmation_store(context: AgentRuntimeContext):
    store = context.confirmation_store
    if store is None:
        raise RuntimeError("Confirmation store is not configured")
    return store


async def execute_tool_node(
    state: AgentState,
    runtime: Runtime[AgentRuntimeContext],
) -> dict[str, object]:
    context = runtime.context
    executor = context.tool_executor
    if executor is None:
        raise RuntimeError("Tool executor is not configured")
    tool_name = state.get("tool_name")
    if not tool_name:
        raise RuntimeError("Tool name is missing")

    result = await executor.execute(
        tool_name,
        state.get("tool_args", {}),
        ToolContext(
            user=context.user,
            session=context.session,
            settings=context.settings,
            conversation_id=UUID(state["conversation_id"]),
            confirmation_store=_confirmation_store(context),
        ),
    )
    return {
        "tool_result": asdict(result),
        "pending_action": result.pending_action,
        "tool_call_count": state.get("tool_call_count", 0) + 1,
    }


async def tool_answer_node(
    state: AgentState,
    runtime: Runtime[AgentRuntimeContext],
) -> dict[str, object]:
    result = state.get("tool_result") or {}
    pending_action = state.get("pending_action")
    if pending_action:
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
    return "execute_tool" if state.get("tool_name") else "validate_output"

