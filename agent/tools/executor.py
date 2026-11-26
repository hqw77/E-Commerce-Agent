"""Tool 执行器.

文件职责:
- 从 Registry 白名单中解析 Tool.
- 用 Pydantic 校验模型生成的参数.
- 限制单轮调用次数, 并记录 Tool Trace.
- 把真正的业务执行交给 Tool handler, handler 再调用 Service.

核心边界:
Executor 不直接访问数据库, 也不实现业务规则.
"""

from __future__ import annotations

import time
from typing import Any

from app.core.exceptions import AppException
from pydantic import ValidationError

from agent.observability.redaction import redact_payload
from agent.tools.context import ToolContext
from agent.tools.errors import (
    AgentToolArgumentError,
    AgentToolExecutionError,
    AgentToolLimitError,
    ToolResult,
)
from agent.tools.registry import RegisteredTool, ToolRegistry


class ToolExecutor:
    """受控执行 Agent Tool 的请求级执行器."""

    def __init__(
        self,
        registry: ToolRegistry,
        *,
        max_calls: int,
    ) -> None:
        """初始化执行器.

        Args:
            registry: Tool 白名单注册表.
            max_calls: 单轮最多允许调用的 Tool 次数.
        """
        self.registry = registry
        self.max_calls = max_calls
        self.calls_used = 0

    @staticmethod
    def _risk_level(tool: RegisteredTool | None) -> str | None:
        """按 Tool 类型给出 Trace 风险等级."""
        if tool is None:
            return None
        return "LOW" if tool.kind == "READ" else "MEDIUM"

    async def execute(
        self,
        tool_name: str,
        raw_args: dict[str, Any],
        context: ToolContext,
    ) -> ToolResult:
        """校验并执行一个 Tool.

        Args:
            tool_name: 模型返回的工具名.
            raw_args: 模型返回的原始参数.
            context: 当前请求的可信依赖.

        Returns:
            ToolResult. 业务异常通常转成 ok=False 的结果, 未知异常继续抛出.

        Raises:
            AgentToolLimitError: 超过单轮调用次数.
            AgentToolNotFoundError: 工具名不在白名单.
            AgentToolArgumentError: 参数不符合 Pydantic Schema.
            AgentToolExecutionError: handler 抛出未分类异常.
        """
        trace = context.trace
        trace_route = context.route or "TOOL"
        started = time.perf_counter()

        if trace is not None:
            trace.emit(
                "tool_start",
                node_name="execute_tool",
                route=trace_route,
                tool_name=tool_name,
                arguments_summary=raw_args,
                execution_status="STARTED",
            )

        if self.calls_used >= self.max_calls:
            # ① 每轮限制 Tool 调用次数, 防止模型循环调用或无限重试.
            if trace is not None:
                trace.emit(
                    "tool_error",
                    node_name="execute_tool",
                    route=trace_route,
                    tool_name=tool_name,
                    arguments_summary=raw_args,
                    execution_status="ERROR",
                    duration_ms=round(
                        (time.perf_counter() - started) * 1000,
                        2,
                    ),
                    error_code="AGENT_TOOL_LIMIT_EXCEEDED",
                )
            raise AgentToolLimitError()
        self.calls_used += 1

        # ② 工具名必须命中 Registry 白名单.
        try:
            tool = self.registry.get(tool_name)
        except AppException as exc:
            if trace is not None:
                trace.emit(
                    "tool_error",
                    node_name="execute_tool",
                    route=trace_route,
                    tool_name=tool_name,
                    arguments_summary=raw_args,
                    execution_status="ERROR",
                    duration_ms=round(
                        (time.perf_counter() - started) * 1000,
                        2,
                    ),
                    error_code=exc.code,
                )
            raise

        # ③ 参数必须通过 Pydantic 校验.
        try:
            args = tool.args_schema.model_validate(raw_args)
        except ValidationError as exc:
            if trace is not None:
                trace.emit(
                    "tool_error",
                    node_name="execute_tool",
                    route=trace_route,
                    tool_name=tool_name,
                    arguments_summary=raw_args,
                    risk_level=self._risk_level(tool),
                    execution_status="ERROR",
                    duration_ms=round(
                        (time.perf_counter() - started) * 1000,
                        2,
                    ),
                    error_code="AGENT_TOOL_ARGUMENT_INVALID",
                )
            raise AgentToolArgumentError() from exc

        # ④ handler 内部调用 Business Service; Executor 不直接访问数据库.
        try:
            result = await tool.handler(context, args)
        except AppException as exc:
            result = ToolResult(
                ok=False,
                tool=tool_name,
                error_code=exc.code,
                error_message=exc.message,
            )
            if trace is not None:
                trace.emit(
                    "tool_end",
                    node_name="execute_tool",
                    route=trace_route,
                    tool_name=tool_name,
                    arguments_summary=raw_args,
                    risk_level=self._risk_level(tool),
                    execution_status="ERROR",
                    duration_ms=round(
                        (time.perf_counter() - started) * 1000,
                        2,
                    ),
                    result_summary=redact_payload(result.data),
                    error_code=exc.code,
                )
            return result
        except Exception as exc:
            if trace is not None:
                trace.emit(
                    "tool_error",
                    node_name="execute_tool",
                    route=trace_route,
                    tool_name=tool_name,
                    arguments_summary=raw_args,
                    risk_level=self._risk_level(tool),
                    execution_status="ERROR",
                    duration_ms=round(
                        (time.perf_counter() - started) * 1000,
                        2,
                    ),
                    error_code="AGENT_TOOL_EXECUTION_FAILED",
                )
            raise AgentToolExecutionError() from exc

        # ⑤ 统一记录 Tool 结束事件和脱敏后的结果摘要.
        if trace is not None:
            trace.emit(
                "tool_end",
                node_name="execute_tool",
                route=trace_route,
                tool_name=tool_name,
                arguments_summary=raw_args,
                risk_level=self._risk_level(tool),
                execution_status="SUCCESS" if result.ok else "ERROR",
                duration_ms=round(
                    (time.perf_counter() - started) * 1000,
                    2,
                ),
                result_summary=(
                    redact_payload(result.data)
                    if result.data
                    else {"confirmation_required": bool(result.pending_action)}
                ),
                error_code=result.error_code,
            )
        return result
