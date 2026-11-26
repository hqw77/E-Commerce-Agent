"""结构化日志配置.

文件职责:
- 用 structlog 生成 key-value 事件.
- 开发环境输出可读 console, 生产环境输出 JSON.
- 把 trace_id 等上下文自动合并到每条日志.

核心边界:
日志不得写入密码, Token, Prompt 或完整业务隐私.
"""

import logging
import logging.config
import sys

import structlog

from app.core.config import settings


def setup_logging() -> None:
    """配置标准 logging 和 structlog, 应用启动时调用一次."""
    log_level = settings.log_level

    renderer: structlog.types.Processor

    # ① JSON 便于集中式日志检索, console 便于本地开发.
    if settings.log_format == "json":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(
            colors=sys.stderr.isatty(),
        )

    shared_processors: list[structlog.types.Processor] = [
        # 把请求上下文中的 trace_id 等字段自动合并到每条日志.
        structlog.contextvars.merge_contextvars,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    # ② 第三方库和业务日志统一走标准 logging handler.
    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "structured": {
                    "()": lambda: formatter,
                },
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "stream": "ext://sys.stdout",
                    "formatter": "structured",
                },
            },
            "root": {
                "handlers": ["console"],
                "level": log_level,
            },
        }
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """返回带模块名的结构化 logger."""
    return structlog.get_logger(name)
