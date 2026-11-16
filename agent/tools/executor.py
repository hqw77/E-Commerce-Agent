"""Validated Tool execution with a per-request call limit."""

from __future__ import annotations

from typing import Any

from app.core.exceptions import AppException
from pydantic import ValidationError

from agent.tools.context import ToolContext
from agent.tools.errors import (
    AgentToolArgumentError,
    AgentToolExecutionError,
    AgentToolLimitError,
    ToolResult,
)
from agent.tools.registry import ToolRegistry


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

    async def execute(
        self,
        tool_name: str,
        raw_args: dict[str, Any],
        context: ToolContext,
    ) -> ToolResult:
        if self.calls_used >= self.max_calls:
            raise AgentToolLimitError()
        self.calls_used += 1
        tool = self.registry.get(tool_name)
        try:
            args = tool.args_schema.model_validate(raw_args)
        except ValidationError as exc:
            raise AgentToolArgumentError() from exc

        try:
            return await tool.handler(context, args)
        except AppException as exc:
            return ToolResult(
                ok=False,
                tool=tool_name,
                error_code=exc.code,
                error_message=exc.message,
            )
        except Exception as exc:
            raise AgentToolExecutionError() from exc
