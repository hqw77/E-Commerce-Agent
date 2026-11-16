"""Agent test isolation for the process-wide Redis client."""

import pytest_asyncio
from app.core.config import settings
from app.db.redis import redis_client
from redis.asyncio import ConnectionPool


def _new_pool() -> ConnectionPool:
    password = (
        settings.redis_password.get_secret_value()
        if settings.redis_password
        else None
    )
    return ConnectionPool(
        host=settings.redis_host,
        port=settings.redis_port,
        db=settings.redis_db,
        password=password or None,
        decode_responses=True,
        max_connections=20,
        socket_connect_timeout=5,
        socket_timeout=5,
        health_check_interval=30,
    )


async def _reset_pool() -> None:
    """Detach or replace connections tied to a previous pytest event loop."""
    try:
        await redis_client.connection_pool.disconnect()
    except RuntimeError:
        # pytest-asyncio may hand this module a new loop while the process-wide
        # pool still references transports from a closed loop. Replace the pool
        # so subsequent tests get fresh, current-loop connections.
        redis_client.connection_pool = _new_pool()


@pytest_asyncio.fixture(scope="module", autouse=True, loop_scope="module")
async def reset_redis_connections():
    """Detach connections that may belong to a previous test loop."""
    await _reset_pool()
    yield
    await _reset_pool()
