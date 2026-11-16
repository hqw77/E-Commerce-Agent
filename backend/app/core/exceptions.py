from typing import Any


class AppException(Exception):
    """Base exception for all application-level exceptions."""

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
    """Exception raised for expected business rule violations."""

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
    """Exception raised for business-level request validation failures."""

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
    """Exception raised when authentication fails."""

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
    """Exception raised when a token has expired."""

    def __init__(self, message: str = "Access token has expired") -> None:
        super().__init__(
            message=message,
            code="TOKEN_EXPIRED",
        )


class InvalidTokenException(AuthenticationException):
    """Exception raised when a token is invalid."""

    def __init__(self, message: str = "Invalid access token") -> None:
        super().__init__(
            message=message,
            code="INVALID_TOKEN",
        )


class PermissionDeniedException(AppException):
    """Exception raised when permission is insufficient."""

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
    """Exception raised when a requested resource does not exist."""

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
    """Exception raised when a resource conflicts with existing data."""

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
