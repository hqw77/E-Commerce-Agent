"""LangGraph 节点的透明 Trace 包装.

文件职责:
- 在不改变节点输入输出和边的条件下记录 node_start/node_end/node_error.
- 把异常映射为稳定 error_code.
- 从 state 的 intent 推导 Trace 路由标签.

核心边界:
Trace 只做观测; collector 失败不能影响节点执行.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from functools import wraps

from app.core.exceptions import AppException
from langgraph.runtime import Runtime

from agent.context import AgentRuntimeContext
from agent.state import AgentState

# 所有 Graph 节点统一的可调用签名.
NodeCallable = Callable[
    [AgentState, Runtime[AgentRuntimeContext]],
    Awaitable[dict[str, object]],
]


def route_for_intent(intent: object) -> str | None:
    """把意图映射为调试台使用的路由标签."""
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
    """把异常映射为 Trace 中的稳定错误码."""
    if isinstance(exc, AppException):
        return exc.code
    if isinstance(exc, TimeoutError):
        return "AGENT_EXECUTION_TIMEOUT"
    return "AGENT_INTERNAL_ERROR"


def instrument_node(name: str, node: NodeCallable) -> NodeCallable:
    """包装节点, 在开始, 成功和异常时写 Trace.

    Args:
        name: 节点名, 写入 node_name.
        node: 原始 Graph 节点.

    Returns:
        保持原签名的包装函数.
    """

    @wraps(node)
    async def wrapped(
        state: AgentState,
        runtime: Runtime[AgentRuntimeContext],
    ) -> dict[str, object]:
        trace = runtime.context.trace
        started = time.perf_counter()
        intent = state.get("intent")
        route = route_for_intent(intent)
        # ① 节点开始; Trace 为空时直接跳过.
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
            # ② 异常也要记录, 然后原样抛出, 不改变 Graph 错误语义.
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

        # ③ 节点可能更新 intent, 所以用最终 state 重新推导 route.
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
