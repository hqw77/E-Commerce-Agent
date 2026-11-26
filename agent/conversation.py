"""Agent 会话的 Redis 持久化与锁.

文件职责:
- 按 user_id + conversation_id 隔离会话.
- 用 Redis 保存最近若干轮历史.
- 用带 TTL 的锁保证同一会话串行处理.
- 用 Lua 脚本原子校验锁 token 后再写历史.

核心流程:
load -> acquire_lock -> 执行 Graph -> save_if_locked -> release_lock.

边界:
本模块是唯一直接读写 conversation Redis key 的 Agent 组件.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.core.config import Settings, get_settings
from app.db.redis import redis_client
from redis.asyncio import Redis
from redis.exceptions import RedisError

from agent.exceptions import (
    AgentConversationLockLostError,
    AgentConversationNotFoundError,
    AgentConversationUnavailableError,
)
from agent.state import HistoryMessage

logger = logging.getLogger(__name__)

# 只有仍持有旧 token 的请求才能释放锁, 避免误删别人的锁.
_RELEASE_LOCK_SCRIPT = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
end
return 0
"""

# 校验锁 token 和写会话必须在同一个 Lua 脚本中完成, 防止检查后锁过期.
_SAVE_IF_LOCKED_SCRIPT = """
if redis.call('GET', KEYS[1]) ~= ARGV[1] then
    return 0
end
redis.call('SET', KEYS[2], ARGV[2], 'EX', ARGV[3])
return 1
"""


@dataclass(slots=True)
class Conversation:
    """一个用户会话的内存表示.

    Args:
        conversation_id: 对外会话 ID.
        user_id: 会话所属用户.
        messages: 已裁剪的历史消息.
        created_at: 首次创建时间.
        updated_at: 最近一次写入时间.
    """

    conversation_id: UUID
    user_id: int
    messages: list[HistoryMessage]
    created_at: datetime
    updated_at: datetime


class ConversationStore:
    """会话 Redis key 的唯一读写入口."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        redis: Redis | None = None,
    ) -> None:
        """允许注入测试 Redis 和配置."""
        self.settings = settings or get_settings()
        self.redis = redis or redis_client

    @staticmethod
    def conversation_key(user_id: int, conversation_id: UUID) -> str:
        """会话内容的 Redis key; user_id 防止跨用户读取."""
        return f"agent:conversation:{user_id}:{conversation_id}"

    @staticmethod
    def lock_key(user_id: int, conversation_id: UUID) -> str:
        """会话锁的 Redis key."""
        return f"agent:conversation:lock:{user_id}:{conversation_id}"

    async def load(
        self,
        *,
        user_id: int,
        conversation_id: UUID,
        create: bool,
    ) -> Conversation:
        """读取会话; create=True 时允许返回空的新会话.

        Raises:
            AgentConversationNotFoundError: 会话不存在或属于其他用户.
            AgentConversationUnavailableError: Redis 或数据格式异常.
        """
        key = self.conversation_key(user_id, conversation_id)
        try:
            raw = await self.redis.get(key)
        except RedisError as exc:
            raise AgentConversationUnavailableError() from exc

        # ① 没有历史时, 只有显式允许创建才返回新会话.
        if raw is None:
            if not create:
                raise AgentConversationNotFoundError()
            now = datetime.now(UTC)
            return Conversation(
                conversation_id=conversation_id,
                user_id=user_id,
                messages=[],
                created_at=now,
                updated_at=now,
            )

        # ② 解析并再次校验 user_id, 防止 key 猜中造成越权.
        try:
            data = json.loads(raw)
            stored_user_id = int(data["user_id"])
            if stored_user_id != user_id:
                raise AgentConversationNotFoundError()
            messages = [
                HistoryMessage(role=item["role"], content=item["content"])
                for item in data["messages"]
            ]
            created_at = datetime.fromisoformat(data["created_at"])
            updated_at = datetime.fromisoformat(data["updated_at"])
        except AgentConversationNotFoundError:
            raise
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise AgentConversationUnavailableError() from exc

        return Conversation(
            conversation_id=conversation_id,
            user_id=user_id,
            messages=messages,
            created_at=created_at,
            updated_at=updated_at,
        )

    async def acquire_lock(
        self,
        *,
        user_id: int,
        conversation_id: UUID,
        token: str,
    ) -> bool:
        """用 SET NX PX 获取会话锁; 返回 False 表示会话正忙."""
        try:
            result = await self.redis.set(
                self.lock_key(user_id, conversation_id),
                token,
                nx=True,
                px=self.settings.agent_conversation_lock_ttl_ms,
            )
        except RedisError as exc:
            raise AgentConversationUnavailableError() from exc
        return bool(result)

    async def release_lock(
        self,
        *,
        user_id: int,
        conversation_id: UUID,
        token: str,
    ) -> bool:
        """仅当 token 匹配时释放锁; 释放失败只记录日志."""
        try:
            result = await self.redis.eval(
                _RELEASE_LOCK_SCRIPT,
                1,
                self.lock_key(user_id, conversation_id),
                token,
            )
        except RedisError as exc:
            logger.warning("agent_lock_release_failed", exc_info=exc)
            return False
        return bool(result)

    async def save_if_locked(
        self,
        *,
        conversation: Conversation,
        token: str,
    ) -> bool:
        """原子校验锁 token 并写入会话.

        Returns:
            True 表示 token 仍有效且已经写入; False 表示锁已丢失.
        """
        # ① 只保留最近 N 条, 防止 Redis value 无限增长.
        messages = conversation.messages[-self.settings.agent_max_history_messages :]
        now = datetime.now(UTC)
        payload = {
            "conversation_id": str(conversation.conversation_id),
            "user_id": conversation.user_id,
            "messages": [
                {"role": message.role, "content": message.content}
                for message in messages
            ],
            "created_at": conversation.created_at.isoformat(),
            "updated_at": now.isoformat(),
        }
        try:
            # ② Lua 中先 GET 校验 token, 再 SET 会话并刷新 TTL.
            result = await self.redis.eval(
                _SAVE_IF_LOCKED_SCRIPT,
                2,
                self.lock_key(conversation.user_id, conversation.conversation_id),
                self.conversation_key(
                    conversation.user_id,
                    conversation.conversation_id,
                ),
                token,
                json.dumps(payload, ensure_ascii=False),
                self.settings.agent_conversation_ttl_seconds,
            )
        except RedisError as exc:
            raise AgentConversationUnavailableError() from exc
        return bool(result)

    async def require_lock_for_save(
        self,
        *,
        conversation: Conversation,
        token: str,
    ) -> None:
        """写入会话; 锁已丢失时抛错, 让本次请求失败而不是覆盖别人."""
        if not await self.save_if_locked(conversation=conversation, token=token):
            raise AgentConversationLockLostError()


def new_conversation_id() -> UUID:
    """生成新的会话 ID."""
    return uuid4()
