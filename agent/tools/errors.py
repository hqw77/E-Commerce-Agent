"""Tool 层异常和安全结果结构.

文件职责:
- 把工具不存在, 参数非法, 超限, 执行失败和确认失败映射为稳定错误码.
- 定义写回 Graph 和模型的 ToolResult.

核心边界:
异常消息不能包含 SQL, 内部路径或模型 Prompt.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core.exceptions import AppException


class AgentToolError(AppException):
    """Tool 层异常基类."""


class AgentToolNotFoundError(AgentToolError):
    """工具名不在白名单时抛出."""
    def __init__(self) -> None:
        """初始化实例依赖."""
        super().__init__(
            message="Agent tool was not found",
            code="AGENT_TOOL_NOT_FOUND",
            status_code=404,
        )


class AgentToolArgumentError(AgentToolError):
    """模型参数未通过 Tool Schema 时抛出."""
    def __init__(self, message: str = "Agent tool arguments are invalid") -> None:
        """初始化实例依赖."""
        super().__init__(
            message=message,
            code="AGENT_TOOL_ARGUMENT_INVALID",
            status_code=422,
        )


class AgentToolLimitError(AgentToolError):
    """单次请求 Tool 调用次数超限时抛出."""
    def __init__(self) -> None:
        """初始化实例依赖."""
        super().__init__(
            message="Agent tool call limit was exceeded",
            code="AGENT_TOOL_LIMIT_EXCEEDED",
            status_code=429,
        )


class AgentToolExecutionError(AgentToolError):
    """Tool handler 执行失败时抛出."""
    def __init__(self, message: str = "Agent tool execution failed") -> None:
        """初始化实例依赖."""
        super().__init__(
            message=message,
            code="AGENT_TOOL_EXECUTION_FAILED",
            status_code=503,
        )


class AgentConfirmationNotFoundError(AgentToolError):
    """确认记录不存在时抛出."""
    def __init__(self) -> None:
        """初始化实例依赖."""
        super().__init__(
            message="Agent action confirmation was not found",
            code="AGENT_ACTION_CONFIRMATION_NOT_FOUND",
            status_code=404,
        )


class AgentConfirmationExpiredError(AgentToolError):
    """确认记录已过期时抛出."""
    def __init__(self) -> None:
        """初始化实例依赖."""
        super().__init__(
            message="Agent action confirmation has expired",
            code="AGENT_ACTION_CONFIRMATION_EXPIRED",
            status_code=410,
        )


class AgentConfirmationConsumedError(AgentToolError):
    """确认记录已被消费时抛出."""
    def __init__(self) -> None:
        """初始化实例依赖."""
        super().__init__(
            message="Agent action confirmation has already been consumed",
            code="AGENT_ACTION_CONFIRMATION_CONSUMED",
            status_code=409,
        )


class AgentConfirmationMismatchError(AgentToolError):
    """确认记录与当前用户或参数不匹配时抛出."""
    def __init__(self) -> None:
        """初始化实例依赖."""
        super().__init__(
            message="Agent action confirmation does not match this user",
            code="AGENT_ACTION_CONFIRMATION_MISMATCH",
            status_code=409,
        )


class AgentConfirmationUnavailableError(AgentToolError):
    """确认存储不可用时抛出."""
    def __init__(self) -> None:
        """初始化实例依赖."""
        super().__init__(
            message="Agent action confirmation service is unavailable",
            code="AGENT_ACTION_CONFIRMATION_UNAVAILABLE",
            status_code=503,
        )


@dataclass(frozen=True, slots=True)
class ToolResult:
    """写回 Graph 和模型的工具结果.

    Args:
        ok: 是否成功.
        tool: 工具名.
        data: 成功时的结构化结果.
        error_code: 失败时的稳定错误码.
        error_message: 可安全展示的错误消息.
        pending_action: PREPARE 工具生成的待确认动作.
    """

    ok: bool
    tool: str
    data: dict[str, Any] = field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None
    pending_action: dict[str, Any] | None = None
