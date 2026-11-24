"""Transparent LangGraph node instrumentation.

The wrapper records node boundaries without changing node outputs, graph edges,
or Tool/RAG semantics.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from functools import wraps

from app.core.exceptions import AppException
from langgraph.runtime import Runtime

from agent.context import AgentRuntimeContext
from agent.state import AgentState

NodeCallable = Callable[
    [AgentState, Runtime[AgentRuntimeContext]],
    Awaitable[dict[str, object]],
]


def route_for_intent(intent: object) -> str | None:
    """Map the current intent vocabulary to a trace route label."""
    if intent == "GENERAL":
        return "GENERAL"
    if intent in {"RAG", "KNOWLEDGE"}:
        return "RAG"
    if intent == "TOOL":
        return "TOOL"
    if intent == "WORKFLOW":
        return "WORKFLOW"
    if intent == "UNSUPPORTED_ACTION":
        return "UNSUPPORTED"
    return None


def _error_code(exc: Exception) -> str:
    if isinstance(exc, AppException):
        return exc.code
    if isinstance(exc, TimeoutError):
        return "AGENT_EXECUTION_TIMEOUT"
    return "AGENT_INTERNAL_ERROR"


def instrument_node(name: str, node: NodeCallable) -> NodeCallable:
    """Return a node wrapper that emits start/end/error trace events."""

    @wraps(node)
    async def wrapped(
        state: AgentState,
        runtime: Runtime[AgentRuntimeContext],
    ) -> dict[str, object]:
        trace = runtime.context.trace
        started = time.perf_counter()
        intent = state.get("intent")
        route = route_for_intent(intent)
        if trace is not None:
            trace.emit(
                "node_start",
                node_name=name,
                intent=str(intent) if intent is not None else None,
                route=route,
                execution_status="STARTED",
            )

        try:
            result = await node(state, runtime)
        except Exception as exc:
            if trace is not None:
                trace.emit(
                    "node_error",
                    node_name=name,
                    intent=str(intent) if intent is not None else None,
                    route=route,
                    execution_status="ERROR",
                    duration_ms=round(
                        (time.perf_counter() - started) * 1000,
                        2,
                    ),
                    error_code=_error_code(exc),
                )
            raise

        final_intent = result.get("intent", intent)
        final_route = route_for_intent(final_intent)
        if trace is not None:
            trace.emit(
                "node_end",
                node_name=name,
                intent=(
                    str(final_intent) if final_intent is not None else None
                ),
                route=final_route,
                execution_status="SUCCESS",
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
                result_summary={"result_keys": sorted(result.keys())},
            )
        return result

    return wrapped
