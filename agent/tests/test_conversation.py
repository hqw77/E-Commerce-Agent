"""Redis conversation lock, atomic write, and rate-limit tests."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from uuid import uuid4

import pytest

pytestmark = pytest.mark.asyncio(loop_scope="module")

from app.db.redis import redis_client

from agent.conversation import Conversation, ConversationStore
from agent.exceptions import (
    AgentConversationLockLostError,
    AgentConversationNotFoundError,
    AgentRateLimitExceededError,
)
from agent.rate_limit import RedisRateLimiter
from agent.state import HistoryMessage
from agent.tests.fakes import make_settings


async def cleanup_conversation(
    store: ConversationStore,
    *,
    user_id: int,
    conversation_id,
) -> None:
    await redis_client.delete(
        store.conversation_key(user_id, conversation_id),
        store.lock_key(user_id, conversation_id),
    )


async def test_lock_save_is_atomic_and_requires_owner_token() -> None:
    settings = make_settings(agent_rate_limit_per_minute=1000)
    store = ConversationStore(settings)
    user_id = uuid4().int
    conversation_id = uuid4()
    lock_token = uuid4().hex
    other_token = uuid4().hex

    try:
        assert await store.acquire_lock(
            user_id=user_id,
            conversation_id=conversation_id,
            token=lock_token,
        )
        assert not await store.acquire_lock(
            user_id=user_id,
            conversation_id=conversation_id,
            token=other_token,
        )

        conversation = Conversation(
            conversation_id=conversation_id,
            user_id=user_id,
            messages=[HistoryMessage(role="user", content="hello")],
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        assert not await store.save_if_locked(
            conversation=conversation,
            token=other_token,
        )
        with pytest.raises(AgentConversationNotFoundError):
            await store.load(
                user_id=user_id,
                conversation_id=conversation_id,
                create=False,
            )

        assert await store.save_if_locked(
            conversation=conversation,
            token=lock_token,
        )
        loaded = await store.load(
            user_id=user_id,
            conversation_id=conversation_id,
            create=False,
        )
        assert loaded.messages == conversation.messages

        assert not await store.release_lock(
            user_id=user_id,
            conversation_id=conversation_id,
            token=other_token,
        )
        assert await store.release_lock(
            user_id=user_id,
            conversation_id=conversation_id,
            token=lock_token,
        )
        assert not await store.save_if_locked(
            conversation=conversation,
            token=lock_token,
        )
    finally:
        await cleanup_conversation(
            store,
            user_id=user_id,
            conversation_id=conversation_id,
        )


async def test_new_conversation_is_created_and_existing_one_must_exist() -> None:
    store = ConversationStore(make_settings())
    user_id = uuid4().int
    conversation_id = uuid4()
    try:
        created = await store.load(
            user_id=user_id,
            conversation_id=conversation_id,
            create=True,
        )
        assert created.messages == []
        with pytest.raises(AgentConversationNotFoundError):
            await ConversationStore(make_settings()).load(
                user_id=user_id,
                conversation_id=uuid4(),
                create=False,
            )
    finally:
        await cleanup_conversation(
            store,
            user_id=user_id,
            conversation_id=conversation_id,
        )


async def test_require_lock_for_save_raises_lock_lost() -> None:
    store = ConversationStore(make_settings())
    user_id = uuid4().int
    conversation_id = uuid4()
    conversation = Conversation(
        conversation_id=conversation_id,
        user_id=user_id,
        messages=[],
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    try:
        with pytest.raises(AgentConversationLockLostError):
            await store.require_lock_for_save(
                conversation=conversation,
                token="missing",
            )
    finally:
        await cleanup_conversation(
            store,
            user_id=user_id,
            conversation_id=conversation_id,
        )


async def test_rate_limit_is_atomic_and_returns_retry_after() -> None:
    settings = make_settings(agent_rate_limit_per_minute=1)
    limiter = RedisRateLimiter(settings)
    user_id = uuid4().int
    bucket = int(time.time()) // 60
    key = f"agent:rate:{user_id}:{bucket}"
    try:
        await limiter.check(user_id)
        with pytest.raises(AgentRateLimitExceededError) as exc_info:
            await limiter.check(user_id)
        assert exc_info.value.status_code == 429
        assert exc_info.value.headers
    finally:
        await redis_client.delete(key)
