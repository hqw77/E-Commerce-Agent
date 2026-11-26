"""Agent 层异常定义.

文件职责:
- 把 LLM, 输入, 会话, 限流和执行错误映射为稳定的 HTTP 错误码.
- 让 API 层返回统一的 AppException 结构.
- 避免把供应商原始错误直接暴露给用户.

核心边界:
异常只描述失败类型, 不包含 prompt, token 或用户隐私.
"""

from app.core.exceptions import AppException


class AgentLLMError(AppException):
    """Agent LLM 调用异常基类."""


class AgentLLMConfigurationError(AgentLLMError):
    """DeepSeek Provider 未配置 API Key 时抛出."""

    def __init__(self, message: str = "DeepSeek LLM is not configured") -> None:
        """初始化实例依赖."""
        super().__init__(
            message=message,
            code="AGENT_LLM_NOT_CONFIGURED",
            status_code=503,
        )


class AgentLLMTimeoutError(AgentLLMError):
    """模型调用超过配置超时时抛出."""

    def __init__(self, message: str = "DeepSeek LLM request timed out") -> None:
        """初始化实例依赖."""
        super().__init__(
            message=message,
            code="AGENT_LLM_TIMEOUT",
            status_code=504,
        )


class AgentLLMUnavailableError(AgentLLMError):
    """模型供应商无法完成请求时抛出."""

    def __init__(self, message: str = "DeepSeek LLM is unavailable") -> None:
        """初始化实例依赖."""
        super().__init__(
            message=message,
            code="AGENT_LLM_UNAVAILABLE",
            status_code=503,
        )


class AgentLLMResponseError(AgentLLMError):
    """模型没有返回可用文本时抛出."""

    def __init__(self, message: str = "DeepSeek LLM returned an empty response") -> None:
        """初始化实例依赖."""
        super().__init__(
            message=message,
            code="AGENT_LLM_RESPONSE_INVALID",
            status_code=502,
        )


class AgentInputInvalidError(AppException):
    """用户消息为空或超过输入上限时抛出."""

    def __init__(self, message: str = "Agent input is invalid") -> None:
        """初始化实例依赖."""
        super().__init__(
            message=message,
            code="AGENT_INPUT_INVALID",
            status_code=422,
        )


class AgentContextBudgetExceededError(AppException):
    """最新一轮对话已超过上下文预算时抛出."""

    def __init__(self) -> None:
        """初始化实例依赖."""
        super().__init__(
            message="Agent context budget is exceeded",
            code="AGENT_CONTEXT_BUDGET_EXCEEDED",
            status_code=422,
        )


class AgentConversationNotFoundError(AppException):
    """会话不存在或不属于当前用户时抛出."""

    def __init__(self) -> None:
        """初始化实例依赖."""
        super().__init__(
            message="Agent conversation was not found",
            code="AGENT_CONVERSATION_NOT_FOUND",
            status_code=404,
        )


class AgentConversationBusyError(AppException):
    """同一会话已有请求持有锁时抛出."""

    def __init__(self) -> None:
        """初始化实例依赖."""
        super().__init__(
            message="Agent conversation is busy",
            code="AGENT_CONVERSATION_BUSY",
            status_code=409,
            headers={"Retry-After": "1"},
        )


class AgentConversationLockLostError(AppException):
    """请求保存时发现会话锁已丢失时抛出."""

    def __init__(self) -> None:
        """初始化实例依赖."""
        super().__init__(
            message="Agent conversation lock was lost",
            code="AGENT_CONVERSATION_LOCK_LOST",
            status_code=409,
        )


class AgentConversationUnavailableError(AppException):
    """Redis 会话服务不可用时抛出."""

    def __init__(self) -> None:
        """初始化实例依赖."""
        super().__init__(
            message="Agent conversation service is unavailable",
            code="AGENT_CONVERSATION_UNAVAILABLE",
            status_code=503,
        )


class AgentRateLimitExceededError(AppException):
    """用户超过每分钟请求限制时抛出."""

    def __init__(self, retry_after: int = 60) -> None:
        """初始化实例依赖."""
        super().__init__(
            message="Agent request rate limit exceeded",
            code="AGENT_RATE_LIMITED",
            status_code=429,
            headers={"Retry-After": str(max(retry_after, 1))},
        )


class AgentRateLimitUnavailableError(AppException):
    """Redis 限流器不可用时抛出."""

    def __init__(self) -> None:
        """初始化实例依赖."""
        super().__init__(
            message="Agent rate limiter is unavailable",
            code="AGENT_RATE_LIMIT_UNAVAILABLE",
            status_code=503,
        )


class AgentExecutionTimeoutError(AppException):
    """整个 Agent 执行超过截止时间时抛出."""

    def __init__(self) -> None:
        """初始化实例依赖."""
        super().__init__(
            message="Agent execution timed out",
            code="AGENT_EXECUTION_TIMEOUT",
            status_code=504,
        )


class AgentIntentError(AppException):
    """意图分类无法产生安全结果时抛出."""

    def __init__(self) -> None:
        """初始化实例依赖."""
        super().__init__(
            message="Agent intent classification failed",
            code="AGENT_INTENT_UNAVAILABLE",
            status_code=503,
        )


class AgentOutputRejectedError(AppException):
    """输出校验拒绝模型回答时抛出."""

    def __init__(self, message: str = "Agent output was rejected") -> None:
        """初始化实例依赖."""
        super().__init__(
            message=message,
            code="AGENT_OUTPUT_REJECTED",
            status_code=500,
        )


class AgentDisabledError(AppException):
    """配置关闭 Agent 时抛出."""

    def __init__(self) -> None:
        """初始化实例依赖."""
        super().__init__(
            message="Agent is disabled",
            code="AGENT_DISABLED",
            status_code=503,
        )


class AgentInternalError(AppException):
    """未预期失败且不能泄露内部细节时抛出."""

    def __init__(self) -> None:
        """初始化实例依赖."""
        super().__init__(
            message="Agent internal error",
            code="AGENT_INTERNAL_ERROR",
            status_code=500,
        )


