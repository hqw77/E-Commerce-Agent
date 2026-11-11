from redis.asyncio import ConnectionPool, Redis

from app.core.config import settings

from collections.abc import AsyncGenerator


# 1. 获取 Redis 密码
redis_password = (
    settings.redis_password.get_secret_value()
    if settings.redis_password
    else None
)

# 空字符串按无密码处理
redis_password = redis_password or None


# 2. 创建 Redis 异步连接池
redis_pool = ConnectionPool(
    host=settings.redis_host,
    port=settings.redis_port,
    db=settings.redis_db,
    password=redis_password,
    decode_responses=True,
    max_connections=20,
    socket_connect_timeout=5,
    socket_timeout=5,
    health_check_interval=30,
)


# 3. 创建 Redis 异步客户端
redis_client = Redis(
    connection_pool=redis_pool,
)


async def close_redis() -> None:
    """Close Redis client and release connection pool resources."""
    await redis_client.aclose()
    await redis_pool.aclose()

async def get_redis() -> AsyncGenerator[Redis, None]:
    """
    Provide Redis client for FastAPI dependency injection.
    """
    yield redis_client
