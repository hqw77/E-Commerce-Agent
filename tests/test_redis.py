import pytest
from redis.asyncio import Redis

from app.db.redis import get_redis, redis_client

pytestmark = pytest.mark.asyncio(loop_scope="module")

async def test_redis_connection():
    """Test whether Redis is reachable."""
    result = await redis_client.ping()

    assert result is True


async def test_redis_set_and_get():
    """Test Redis basic read and write operations."""
    key = "test:ecommerce-agent:connection"
    value = "hello-redis"

    await redis_client.set(key, value, ex=60)

    result = await redis_client.get(key)

    assert result == value

    await redis_client.delete(key)


async def test_get_redis_dependency():
    """Test Redis dependency injection."""
    generator = get_redis()

    client = await anext(generator)

    assert isinstance(client, Redis)
    assert client is redis_client

    await generator.aclose()
