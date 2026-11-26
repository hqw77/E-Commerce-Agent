"""Agent API 的 Redis 固定窗口限流.

文件职责:
- 按 user_id 和分钟桶计数.
- 用 Lua 保证 INCR 和首次 EXPIRE 原子执行.
- 超限返回 429 和 Retry-After.

核心边界:
这是请求频率保护, 不是业务配额或权限校验.
"""

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

# 第一次写入时设置 60 秒过期, 避免计数器永久占用内存.
_RATE_LIMIT_SCRIPT = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return current
"""


class RedisRateLimiter:
    """基于现有 Redis 客户端的原子固定窗口限流器."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        redis: Redis | None = None,
    ) -> None:
        """允许注入测试 Redis 和配置."""
        self.settings = settings or get_settings()
        self.redis = redis or redis_client

    async def check(self, user_id: int) -> None:
        """增加当前分钟计数, 超限时抛 429.

        Raises:
            AgentRateLimitExceededError: 超过每分钟限制.
            AgentRateLimitUnavailableError: Redis 不可用.
        """
        now = int(time.time())
        # ① 用分钟时间戳分桶, 窗口自然滚动.
        bucket = now // 60
        key = f"agent:rate:{user_id}:{bucket}"
        try:
            # ② Lua 中 INCR 和 EXPIRE 原子完成, 避免计数无 TTL.
            count = await self.redis.eval(
                _RATE_LIMIT_SCRIPT,
                1,
                key,
                60,
            )
        except RedisError as exc:
            raise AgentRateLimitUnavailableError() from exc

        # ③ 超限时计算到下一分钟的自然等待秒数.
        if int(count) > self.settings.agent_rate_limit_per_minute:
            retry_after = 60 - (now % 60)
            raise AgentRateLimitExceededError(retry_after=retry_after)
