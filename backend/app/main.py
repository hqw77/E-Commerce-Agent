
"""FastAPI 应用入口.

负责初始化日志, 注册 lifespan 资源管理, 全局异常处理器和 v1 路由.
业务逻辑不放在这里, 保持应用装配和业务实现分离.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.router import api_router
from app.core.config import settings
from app.core.exception_handlers import register_exception_handlers
from app.core.logging import setup_logging
from app.db.redis import close_redis, redis_client

# 日志必须在创建应用和注册异常处理器之前完成初始化,
# 这样启动期异常也能使用统一格式输出.
setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """管理应用启动和关闭资源."""
    try:
        # 启动时主动 ping Redis, 让连接配置错误尽早暴露, 而不是等首个请求.
        await redis_client.ping()
        yield
    finally:
        # 关闭时释放 Redis 客户端和连接池, 避免进程退出时连接泄漏.
        await close_redis()


# 应用级配置只从 Settings 读取, 不在入口写死环境相关参数.
app = FastAPI(
    title=settings.app_name,
    debug=settings.debug,
    lifespan=lifespan,
)

# 统一异常映射确保所有错误响应结构一致.
register_exception_handlers(app)

# 所有业务路由挂在统一 API 前缀下, 便于网关和版本管理.
app.include_router(
    api_router,
    prefix=settings.api_v1_prefix,
)
