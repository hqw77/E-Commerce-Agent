
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.router import api_router
from app.core.config import settings
from app.core.exception_handlers import register_exception_handlers
from app.core.logging import setup_logging
from app.db.redis import close_redis, redis_client

setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage application startup and shutdown resources."""
    try:
        # Application startup: verify Redis connection.
        await redis_client.ping()
        yield
    finally:
        # Application shutdown: release Redis resources.
        await close_redis()


app = FastAPI(
    title=settings.app_name,
    debug=settings.debug,
    lifespan=lifespan,
)

register_exception_handlers(app)

app.include_router(
    api_router,
    prefix=settings.api_v1_prefix,
)
