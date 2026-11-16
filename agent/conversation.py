"""Redis-backed conversation persistence, locking, and atomic history writes."""

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

_RELEASE_LOCK_SCRIPT = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
end
return 0
"""

_SAVE_IF_LOCKED_SCRIPT = """
if redis.call('GET', KEYS[1]) ~= ARGV[1] then
    return 0
end
redis.call('SET', KEYS[2], ARGV[2], 'EX', ARGV[3])
return 1
"""


@dataclass(slots=True)
class Conversation:
    conversation_id: UUID
    user_id: int
    messages: list[HistoryMessage]
    created_at: datetime
    updated_at: datetime


class ConversationStore:
    """The only Agent component allowed to read/write conversation Redis keys."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        redis: Redis | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.redis = redis or redis_client

    @staticmethod
    def conversation_key(user_id: int, conversation_id: UUID) -> str:
        return f"agent:conversation:{user_id}:{conversation_id}"

    @staticmethod
    def lock_key(user_id: int, conversation_id: UUID) -> str:
        return f"agent:conversation:lock:{user_id}:{conversation_id}"

    async def load(
        self,
        *,
        user_id: int,
        conversation_id: UUID,
        create: bool,
    ) -> Conversation:
        key = self.conversation_key(user_id, conversation_id)
        try:
            raw = await self.redis.get(key)
        except RedisError as exc:
            raise AgentConversationUnavailableError() from exc

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
        """Atomically verify the lock token and write the conversation."""
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
        if not await self.save_if_locked(conversation=conversation, token=token):
            raise AgentConversationLockLostError()


def new_conversation_id() -> UUID:
    return uuid4()
