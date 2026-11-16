"""RuntimeContext API verification against the installed LangGraph version."""

import asyncio
from dataclasses import dataclass
from typing import TypedDict

import pytest
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime


@dataclass(frozen=True)
class RequestContext:
    """Per-request values; deliberately not stored in graph state."""

    request_id: str
    user_id: int
    session_token: str


class RuntimeState(TypedDict, total=False):
    seen_request_id: str
    seen_user_id: int
    seen_session_token: str
    value: str


async def runtime_node(
    state: RuntimeState,
    runtime: Runtime[RequestContext],
) -> dict[str, object]:
    context = runtime.context
    return {
        "seen_request_id": context.request_id,
        "seen_user_id": context.user_id,
        "seen_session_token": context.session_token,
        "value": f"{state['value']}:{context.user_id}",
    }


def build_runtime_graph():
    builder = StateGraph(RuntimeState, context_schema=RequestContext)
    builder.add_node("runtime_node", runtime_node)
    builder.add_edge(START, "runtime_node")
    builder.add_edge("runtime_node", END)
    return builder.compile()


@pytest.mark.asyncio
async def test_langgraph_runtime_context_is_per_invocation() -> None:
    graph = build_runtime_graph()

    first, second = await asyncio.gather(
        graph.ainvoke(
            {"value": "first"},
            context=RequestContext("request-1", 101, "session-1"),
        ),
        graph.ainvoke(
            {"value": "second"},
            context=RequestContext("request-2", 202, "session-2"),
        ),
    )

    assert first["seen_request_id"] == "request-1"
    assert first["seen_user_id"] == 101
    assert first["seen_session_token"] == "session-1"
    assert first["value"] == "first:101"

    assert second["seen_request_id"] == "request-2"
    assert second["seen_user_id"] == 202
    assert second["seen_session_token"] == "session-2"
    assert second["value"] == "second:202"

    assert first["seen_user_id"] != second["seen_user_id"]
    assert first["seen_session_token"] != second["seen_session_token"]
