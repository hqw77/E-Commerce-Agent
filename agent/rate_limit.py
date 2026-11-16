"""Redis atomic per-user rate limiting for the Agent API."""

from __future__ import annotations

import time

from app.core.config import Settings, get_settings
from app.db.redis import redis_client
from redis.asyncio import Redis
from redis.exceptions import RedisError

from agent.exceptions import (
    AgentRateLimitExceededError,
    AgentRateLimitUnavailableError,
)

_RATE_LIMIT_SCRIPT = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return current
"""


class RedisRateLimiter:
    """Atomic fixed-window limiter using the existing Redis client."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        redis: Redis | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.redis = redis or redis_client

    async def check(self, user_id: int) -> None:
        now = int(time.time())
        bucket = now // 60
        key = f"agent:rate:{user_id}:{bucket}"
        try:
            count = await self.redis.eval(
                _RATE_LIMIT_SCRIPT,
                1,
                key,
                60,
            )
        except RedisError as exc:
            raise AgentRateLimitUnavailableError() from exc

        if int(count) > self.settings.agent_rate_limit_per_minute:
            retry_after = 60 - (now % 60)
            raise AgentRateLimitExceededError(retry_after=retry_after)
