"""Agent Tool 注册表.

文件职责:
- 保存工具名到 RegisteredTool 的白名单映射.
- 把 Pydantic 参数 Schema 转成 OpenAI Tool 定义.
- 拒绝重复注册和未注册工具.

核心边界:
Registry 只描述工具, 不执行工具; 执行由 ToolExecutor 负责.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel

from agent.tools.context import ToolContext
from agent.tools.errors import AgentToolNotFoundError, ToolResult

# Tool handler 的固定签名: 可信上下文 + 已校验参数 -> ToolResult.
ToolHandler = Callable[[ToolContext, BaseModel], Awaitable[ToolResult]]


@dataclass(frozen=True, slots=True)
class RegisteredTool:
    """一个注册到白名单的 Tool.

    Args:
        name: 模型可调用的工具名.
        description: 提供给模型的用途说明.
        args_schema: 参数 Pydantic Schema.
        kind: READ 只读或 PREPARE 生成待确认计划.
        handler: 实际执行函数.
    """

    name: str
    description: str
    args_schema: type[BaseModel]
    kind: Literal["READ", "PREPARE"]
    handler: ToolHandler

    def openai_spec(self) -> dict[str, Any]:
        """转换成模型 API 需要的 function tool 定义."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.args_schema.model_json_schema(),
            },
        }


class ToolRegistry:
    """工具名白名单; Executor 只能从这里解析 Tool."""

    def __init__(self) -> None:
        """初始化实例依赖."""
        self._tools: dict[str, RegisteredTool] = {}

    def register(self, tool: RegisteredTool) -> None:
        """注册工具; 同名工具直接拒绝, 防止覆盖已有能力."""
        if tool.name in self._tools:
            raise ValueError(f"Duplicate tool registration: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> RegisteredTool:
        """按名称取工具; 不在白名单时抛 AgentToolNotFoundError."""
        tool = self._tools.get(name)
        if tool is None:
            raise AgentToolNotFoundError()
        return tool

    def names(self) -> frozenset[str]:
        """返回当前允许的工具名集合."""
        return frozenset(self._tools)

    def openai_tools(
        self,
        *,
        kinds: frozenset[str] | None = None,
    ) -> list[dict[str, Any]]:
        """按 READ/PREPARE 类型过滤后生成给模型的工具列表."""
        return [
            tool.openai_spec()
            for tool in self._tools.values()
            if kinds is None or tool.kind in kinds
        ]
