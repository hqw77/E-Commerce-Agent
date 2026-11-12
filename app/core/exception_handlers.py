from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import AppException
from app.core.logging import get_logger

logger = get_logger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    """Register global exception handlers for the FastAPI application."""

    @app.exception_handler(AppException)
    async def app_exception_handler(
        request: Request,
        exc: AppException,
    ) -> JSONResponse:
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
