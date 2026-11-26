"""Redis 异步客户端和连接池.

Redis 在这里主要承载限流, 会话, 分布式锁和临时确认状态. 这些数据的生命周期
通常短于业务数据, 且不应作为订单/库存等业务事实的唯一来源.
"""

from collections.abc import AsyncGenerator

from redis.asyncio import ConnectionPool, Redis

from app.core.config import settings

# SecretStr 需要显式解包, 空字符串按无密码处理, 兼容本地无认证 Redis.
# 1. 获取 Redis 密码
redis_password = (
    settings.redis_password.get_secret_value()
    if settings.redis_password
    else None
)

# 空字符串按无密码处理
redis_password = redis_password or None


# decode_responses=True 让业务层直接拿到 str, 避免到处处理 bytes.
# 超时和健康检查用于快速发现 Redis 不可用, 防止请求无限等待.
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


# Redis 客户端复用连接池, 不应在每个请求中重复创建.
# 3. 创建 Redis 异步客户端
redis_client = Redis(
    connection_pool=redis_pool,
)


async def close_redis() -> None:
    """应用关闭时释放客户端和连接池, 避免连接泄漏."""
    await redis_client.aclose()
    await redis_pool.aclose()


async def get_redis() -> AsyncGenerator[Redis, None]:
    """提供复用进程连接池的 Redis 客户端.

    Yields:
        进程级 Redis 客户端; 调用方不要 close.
    """
    yield redis_client
