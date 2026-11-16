"""Agent-level exceptions for the TASK-006 LLM foundation."""

from app.core.exceptions import AppException


class AgentLLMError(AppException):
    """Base exception for Agent LLM failures."""


class AgentLLMConfigurationError(AgentLLMError):
    """Raised when the DeepSeek provider is not configured."""

    def __init__(self, message: str = "DeepSeek LLM is not configured") -> None:
        super().__init__(
            message=message,
            code="AGENT_LLM_NOT_CONFIGURED",
            status_code=503,
        )


class AgentLLMTimeoutError(AgentLLMError):
    """Raised when a model call exceeds the configured timeout."""

    def __init__(self, message: str = "DeepSeek LLM request timed out") -> None:
        super().__init__(
            message=message,
            code="AGENT_LLM_TIMEOUT",
            status_code=504,
        )


class AgentLLMUnavailableError(AgentLLMError):
    """Raised when the model provider cannot complete a request."""

    def __init__(self, message: str = "DeepSeek LLM is unavailable") -> None:
        super().__init__(
            message=message,
            code="AGENT_LLM_UNAVAILABLE",
            status_code=503,
        )


class AgentLLMResponseError(AgentLLMError):
    """Raised when the model returns no usable text."""

    def __init__(self, message: str = "DeepSeek LLM returned an empty response") -> None:
        super().__init__(
            message=message,
            code="AGENT_LLM_RESPONSE_INVALID",
            status_code=502,
        )


class AgentInputInvalidError(AppException):
    """Raised when the user message is empty or over the input limit."""

    def __init__(self, message: str = "Agent input is invalid") -> None:
        super().__init__(
            message=message,
            code="AGENT_INPUT_INVALID",
            status_code=422,
        )


class AgentContextBudgetExceededError(AppException):
    """Raised when the required latest conversation turn exceeds the budget."""

    def __init__(self) -> None:
        super().__init__(
            message="Agent context budget is exceeded",
            code="AGENT_CONTEXT_BUDGET_EXCEEDED",
            status_code=422,
        )


class AgentConversationNotFoundError(AppException):
    """Raised when a conversation does not exist or belongs to another user."""

    def __init__(self) -> None:
        super().__init__(
            message="Agent conversation was not found",
            code="AGENT_CONVERSATION_NOT_FOUND",
            status_code=404,
        )


class AgentConversationBusyError(AppException):
    """Raised when another request currently owns the conversation lock."""

    def __init__(self) -> None:
        super().__init__(
            message="Agent conversation is busy",
            code="AGENT_CONVERSATION_BUSY",
            status_code=409,
            headers={"Retry-After": "1"},
        )


class AgentConversationLockLostError(AppException):
    """Raised when the request no longer owns the conversation lock."""

    def __init__(self) -> None:
        super().__init__(
            message="Agent conversation lock was lost",
            code="AGENT_CONVERSATION_LOCK_LOST",
            status_code=409,
        )


class AgentConversationUnavailableError(AppException):
    """Raised when the Redis-backed conversation service is unavailable."""

    def __init__(self) -> None:
        super().__init__(
            message="Agent conversation service is unavailable",
            code="AGENT_CONVERSATION_UNAVAILABLE",
            status_code=503,
        )


class AgentRateLimitExceededError(AppException):
    """Raised when the user exceeds the per-minute request limit."""

    def __init__(self, retry_after: int = 60) -> None:
        super().__init__(
            message="Agent request rate limit exceeded",
            code="AGENT_RATE_LIMITED",
            status_code=429,
            headers={"Retry-After": str(max(retry_after, 1))},
        )


class AgentRateLimitUnavailableError(AppException):
    """Raised when the Redis-backed rate limiter is unavailable."""

    def __init__(self) -> None:
        super().__init__(
            message="Agent rate limiter is unavailable",
            code="AGENT_RATE_LIMIT_UNAVAILABLE",
            status_code=503,
        )


class AgentExecutionTimeoutError(AppException):
    """Raised when the complete Agent execution exceeds its deadline."""

    def __init__(self) -> None:
        super().__init__(
            message="Agent execution timed out",
            code="AGENT_EXECUTION_TIMEOUT",
            status_code=504,
        )


class AgentIntentError(AppException):
    """Raised when intent classification cannot produce a safe result."""

    def __init__(self) -> None:
        super().__init__(
            message="Agent intent classification failed",
            code="AGENT_INTENT_UNAVAILABLE",
            status_code=503,
        )


class AgentOutputRejectedError(AppException):
    """Raised when output validation rejects a model response."""

    def __init__(self, message: str = "Agent output was rejected") -> None:
        super().__init__(
            message=message,
            code="AGENT_OUTPUT_REJECTED",
            status_code=500,
        )


class AgentDisabledError(AppException):
    """Raised when the Agent is disabled by configuration."""

    def __init__(self) -> None:
        super().__init__(
            message="Agent is disabled",
            code="AGENT_DISABLED",
            status_code=503,
        )


class AgentInternalError(AppException):
    """Raised for an unexpected Agent failure without leaking internals."""

    def __init__(self) -> None:
        super().__init__(
            message="Agent internal error",
            code="AGENT_INTERNAL_ERROR",
            status_code=500,
        )


