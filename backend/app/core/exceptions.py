"""应用异常体系.

业务层只抛出带有 code 和 status_code 的 AppException 子类, 由统一异常处理器
转换成稳定的 HTTP 响应. 这样可以避免在 Router 里散落 try/except, 也避免把
数据库错误或内部实现直接暴露给客户端.
"""

from typing import Any


class AppException(Exception):
    """
    所有应用异常的基类.

    code 用于客户端和日志做稳定分类, status_code 用于 API 状态码,
    details 只放安全的附加信息, 不应包含密码, token 或内部堆栈.
    """

    def __init__(
        self,
        message: str,
        code: str = "APPLICATION_ERROR",
        status_code: int = 500,
        details: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details
        self.headers = headers

        super().__init__(message)


class BusinessException(AppException):
    """业务规则冲突, 默认映射为 400. 例如请求本身合法但当前业务状态不允许."""

    def __init__(
        self,
        message: str,
        code: str = "BUSINESS_ERROR",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code=code,
            status_code=400,
            details=details,
        )


class ValidationException(AppException):
    """业务层校验失败, 默认映射为 422. 与 Pydantic 请求结构校验区分开."""

    def __init__(
        self,
        message: str = "Validation failed",
        code: str = "VALIDATION_ERROR",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code=code,
            status_code=422,
            details=details,
        )


class AuthenticationException(AppException):
    """认证失败, 默认映射为 401. 默认附带 WWW-Authenticate: Bearer."""

    def __init__(
        self,
        message: str = "Authentication failed",
        details: dict[str, Any] | None = None,
        code: str = "AUTHENTICATION_FAILED",
        headers: dict[str, str] | None = None,
    ) -> None:
        if headers is None:
            headers = {"WWW-Authenticate": "Bearer"}

        super().__init__(
            message=message,
            code=code,
            status_code=401,
            details=details,
            headers=headers,
        )


class TokenExpiredException(AuthenticationException):
    """Access Token 已过期. 单独分类便于前端触发刷新流程."""

    def __init__(self, message: str = "Access token has expired") -> None:
        super().__init__(
            message=message,
            code="TOKEN_EXPIRED",
        )


class InvalidTokenException(AuthenticationException):
    """Token 无效, 包括签名错误, claims 不合法和类型错误."""

    def __init__(self, message: str = "Invalid access token") -> None:
        super().__init__(
            message=message,
            code="INVALID_TOKEN",
        )


class PermissionDeniedException(AppException):
    """已认证但权限不足, 默认映射为 403. 普通用户访问管理员资源时使用."""

    def __init__(
        self,
        message: str = "Permission denied",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code="PERMISSION_DENIED",
            status_code=403,
            details=details,
        )


class ResourceNotFoundException(AppException):
    """资源不存在, 默认映射为 404. 对越权资源也常故意返回 404, 避免泄露存在性."""

    def __init__(
        self,
        message: str = "Resource not found",
        details: dict[str, Any] | None = None,
        code: str = "RESOURCE_NOT_FOUND",
    ) -> None:
        super().__init__(
            message=message,
            code=code,
            status_code=404,
            details=details,
        )


class ConflictException(AppException):
    """资源冲突, 默认映射为 409. 用于幂等键冲突, 非法状态转换和并发冲突."""

    def __init__(
        self,
        message: str = "Resource conflict",
        details: dict[str, Any] | None = None,
        code: str = "RESOURCE_CONFLICT",
    ) -> None:
        super().__init__(
            message=message,
            code=code,
            status_code=409,
            details=details,
        )
