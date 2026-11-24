"""全局异常处理.

所有异常在这里被转换成统一的 JSON 结构, 让前端只依赖 code 和 message,
同时保证未捕获异常只返回通用提示, 不把堆栈和数据库细节泄露给客户端.
"""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import AppException
from app.core.logging import get_logger

logger = get_logger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    """注册应用级异常处理器, 覆盖业务异常, HTTP 异常, 参数校验和兜底异常."""

    @app.exception_handler(AppException)
    async def app_exception_handler(
        request: Request,
        exc: AppException,
    ) -> JSONResponse:
        # 业务异常是预期内的失败, 只记录错误码和路径, 不记录敏感请求体.
        logger.warning(
            "application_exception",
            error_code=exc.code,
            path=request.url.path,
        )

        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
            },
            headers=exc.headers,
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request,
        exc: StarletteHTTPException,
    ) -> JSONResponse:
        # 保留 FastAPI/Starlette 产生的 HTTP 状态码, 但统一响应结构.
        message = (
            exc.detail
            if isinstance(exc.detail, str)
            else "HTTP request failed"
        )

        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "code": "HTTP_ERROR",
                "message": message,
                "details": None,
            },
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        # 把 Pydantic 的 loc 拍平成 field 路径, 方便前端定位具体参数.
        errors: list[dict[str, Any]] = [
            {
                "field": ".".join(str(part) for part in error["loc"]),
                "message": error["msg"],
                "type": error["type"],
            }
            for error in exc.errors()
        ]

        return JSONResponse(
            status_code=422,
            content={
                "success": False,
                "code": "VALIDATION_ERROR",
                "message": "Request validation failed",
                "details": errors,
            },
        )

    @app.exception_handler(Exception)
    async def unexpected_exception_handler(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        # 兜底处理器只记录服务端日志, 对客户端返回固定文案,
        # 避免 SQL, 文件路径, 密钥等内部信息通过错误响应泄露.
        logger.exception(
            "unexpected_server_exception",
            path=request.url.path,
        )

        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "code": "INTERNAL_SERVER_ERROR",
                "message": "Internal server error",
                "details": None,
            },
        )
