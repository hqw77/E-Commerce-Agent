"""Validated Tool execution with a per-request call limit."""

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
    def __init__(
        self,
        registry: ToolRegistry,
        *,
        max_calls: int,
    ) -> None:
        self.registry = registry
        self.max_calls = max_calls
        self.calls_used = 0

    @staticmethod
    def _risk_level(tool: RegisteredTool | None) -> str | None:
        if tool is None:
            return None
        return "LOW" if tool.kind == "READ" else "MEDIUM"

    async def execute(
        self,
        tool_name: str,
        raw_args: dict[str, Any],
        context: ToolContext,
    ) -> ToolResult:
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
