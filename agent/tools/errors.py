"""Tool-specific errors and safe result types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core.exceptions import AppException


class AgentToolError(AppException):
    """Base Tool-layer exception."""


class AgentToolNotFoundError(AgentToolError):
    def __init__(self) -> None:
        super().__init__(
            message="Agent tool was not found",
            code="AGENT_TOOL_NOT_FOUND",
            status_code=404,
        )


class AgentToolArgumentError(AgentToolError):
    def __init__(self, message: str = "Agent tool arguments are invalid") -> None:
        super().__init__(
            message=message,
            code="AGENT_TOOL_ARGUMENT_INVALID",
            status_code=422,
        )


class AgentToolLimitError(AgentToolError):
    def __init__(self) -> None:
        super().__init__(
            message="Agent tool call limit was exceeded",
            code="AGENT_TOOL_LIMIT_EXCEEDED",
            status_code=429,
        )


class AgentToolExecutionError(AgentToolError):
    def __init__(self, message: str = "Agent tool execution failed") -> None:
        super().__init__(
            message=message,
            code="AGENT_TOOL_EXECUTION_FAILED",
            status_code=503,
        )


class AgentConfirmationNotFoundError(AgentToolError):
    def __init__(self) -> None:
        super().__init__(
            message="Agent action confirmation was not found",
            code="AGENT_ACTION_CONFIRMATION_NOT_FOUND",
            status_code=404,
        )


class AgentConfirmationExpiredError(AgentToolError):
    def __init__(self) -> None:
        super().__init__(
            message="Agent action confirmation has expired",
            code="AGENT_ACTION_CONFIRMATION_EXPIRED",
            status_code=410,
        )


class AgentConfirmationConsumedError(AgentToolError):
    def __init__(self) -> None:
        super().__init__(
            message="Agent action confirmation has already been consumed",
            code="AGENT_ACTION_CONFIRMATION_CONSUMED",
            status_code=409,
        )


class AgentConfirmationMismatchError(AgentToolError):
    def __init__(self) -> None:
        super().__init__(
            message="Agent action confirmation does not match this user",
            code="AGENT_ACTION_CONFIRMATION_MISMATCH",
            status_code=409,
        )


class AgentConfirmationUnavailableError(AgentToolError):
    def __init__(self) -> None:
        super().__init__(
            message="Agent action confirmation service is unavailable",
            code="AGENT_ACTION_CONFIRMATION_UNAVAILABLE",
            status_code=503,
        )


@dataclass(frozen=True, slots=True)
class ToolResult:
    """Serializable result returned to the graph and the model."""

    ok: bool
    tool: str
    data: dict[str, Any] = field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None
    pending_action: dict[str, Any] | None = None
