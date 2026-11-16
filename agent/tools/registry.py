"""Tool Registry with a strict name whitelist."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel

from agent.tools.context import ToolContext
from agent.tools.errors import AgentToolNotFoundError, ToolResult

ToolHandler = Callable[[ToolContext, BaseModel], Awaitable[ToolResult]]


@dataclass(frozen=True, slots=True)
class RegisteredTool:
    name: str
    description: str
    args_schema: type[BaseModel]
    kind: Literal["READ", "PREPARE"]
    handler: ToolHandler

    def openai_spec(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.args_schema.model_json_schema(),
            },
        }


class ToolRegistry:
    """The only source of tool names allowed to reach the executor."""

    def __init__(self) -> None:
        self._tools: dict[str, RegisteredTool] = {}

    def register(self, tool: RegisteredTool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Duplicate tool registration: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> RegisteredTool:
        tool = self._tools.get(name)
        if tool is None:
            raise AgentToolNotFoundError()
        return tool

    def names(self) -> frozenset[str]:
        return frozenset(self._tools)

    def openai_tools(self) -> list[dict[str, Any]]:
        return [tool.openai_spec() for tool in self._tools.values()]
