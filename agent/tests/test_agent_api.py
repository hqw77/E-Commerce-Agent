"""Agent API integration tests using real Redis and fake LLM/RAG boundaries."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from app.api.dependencies import get_current_user
from app.api.v1 import agent as agent_api
from app.core.config import get_settings
from app.db.session import AsyncSessionLocal, get_db
from app.main import app
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from agent.conversation import ConversationStore
from agent.rate_limit import RedisRateLimiter
from agent.runtime import AgentRuntime, ChatResult
from agent.tests.fakes import (
    FakeLLM,
    FakeRetrieval,
    make_item,
    make_settings,
    make_user,
)

pytestmark = pytest.mark.asyncio(loop_scope="module")


@pytest_asyncio.fixture(loop_scope="module")
async def redis() -> AsyncIterator[Redis]:
    settings = get_settings()
    client = Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        db=settings.redis_db,
        password=(
            settings.redis_password.get_secret_value()
            if settings.redis_password
            else None
        ),
        decode_responses=True,
    )
    yield client
    await client.aclose()


@pytest_asyncio.fixture(loop_scope="module")
async def api_client(redis: Redis) -> AsyncIterator[AsyncClient]:
    user = make_user(uuid4().int)

    async def fake_user() -> SimpleNamespace:
        return user

    async def override_get_db() -> AsyncIterator[AsyncSession]:
        async with AsyncSessionLocal() as session:
            yield session

    app.dependency_overrides[get_current_user] = fake_user
    app.dependency_overrides[get_db] = override_get_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            client.agent_user = user  # type: ignore[attr-defined]
            yield client
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)
        await cleanup_user(redis, user.id)


async def cleanup_user(redis: Redis, user_id: int) -> None:
    patterns = [
        f"agent:conversation:{user_id}:*",
        f"agent:conversation:lock:{user_id}:*",
        f"agent:rate:{user_id}:*",
    ]
    keys: list[str] = []
    for pattern in patterns:
        keys.extend([key async for key in redis.scan_iter(pattern)])
    if keys:
        await redis.delete(*keys)


def install_runtime(
    monkeypatch: pytest.MonkeyPatch,
    redis: Redis,
    *,
    settings,
    llm=None,
    retrieval=None,
):
    store = ConversationStore(settings, redis=redis)
    limiter = RedisRateLimiter(settings, redis=redis)
    llm = llm or FakeLLM(["GENERAL", "api answer"])
    retrieval = retrieval or FakeRetrieval()

    def factory(*, session, user, settings):
        return AgentRuntime(
            session,
            user,
            settings,
            llm=llm,
            retrieval=retrieval,
            conversation_store=store,
            rate_limiter=limiter,
        )

    monkeypatch.setattr(agent_api, "AgentRuntime", factory)
    monkeypatch.setattr(agent_api, "get_settings", lambda: settings)
    return store, llm, retrieval


async def test_agent_api_requires_authentication(redis: Redis) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/agent/chat",
            json={"message": "hello"},
        )
    assert response.status_code == 401


async def test_general_chat_returns_conversation(
    api_client: AsyncClient,
    redis: Redis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = make_settings()
    install_runtime(monkeypatch, redis, settings=settings)

    response = await api_client.post(
        "/api/v1/agent/chat",
        json={"message": "hello"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["answer"] == "api answer"
    assert body["conversation_id"]
    assert body["message_id"]
    assert body["sources"] == []


async def test_knowledge_chat_returns_backend_sources(
    api_client: AsyncClient,
    redis: Redis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = make_settings()
    item = make_item()
    install_runtime(
        monkeypatch,
        redis,
        settings=settings,
        llm=FakeLLM(["KNOWLEDGE", "knowledge answer"]),
        retrieval=FakeRetrieval([item]),
    )

    response = await api_client.post(
        "/api/v1/agent/chat",
        json={"message": "退款条件是什么？"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["answer"] == "knowledge answer"
    assert body["sources"][0]["chunk_id"] == item.chunk_id
    assert body["sources"][0]["document_id"] == item.document_id


async def test_client_identity_fields_are_rejected(
    api_client: AsyncClient,
) -> None:
    response = await api_client.post(
        "/api/v1/agent/chat",
        json={"message": "hello", "user_id": 999, "is_admin": True},
    )

    assert response.status_code == 422


async def test_foreign_conversation_returns_404(
    api_client: AsyncClient,
    redis: Redis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = make_settings()
    store, _, _ = install_runtime(
        monkeypatch,
        redis,
        settings=settings,
    )
    owner = make_user(uuid4().int)
    conversation_id = uuid4()
    token = uuid4().hex
    await store.acquire_lock(
        user_id=owner.id,
        conversation_id=conversation_id,
        token=token,
    )
    await store.release_lock(
        user_id=owner.id,
        conversation_id=conversation_id,
        token=token,
    )
    # Create a conversation owned by a different user.
    from datetime import UTC, datetime

    from agent.conversation import Conversation

    await store.save_if_locked(
        conversation=Conversation(
            conversation_id=conversation_id,
            user_id=owner.id,
            messages=[],
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        ),
        token=await _acquire_owner_lock(store, owner.id, conversation_id),
    )
    response = await api_client.post(
        "/api/v1/agent/chat",
        json={"message": "hello", "conversation_id": str(conversation_id)},
    )
    assert response.status_code == 404
    await cleanup_user(redis, owner.id)


async def _acquire_owner_lock(store: ConversationStore, user_id: int, cid) -> str:
    token = uuid4().hex
    assert await store.acquire_lock(
        user_id=user_id,
        conversation_id=cid,
        token=token,
    )
    return token


async def test_busy_conversation_returns_409(
    api_client: AsyncClient,
    redis: Redis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = make_settings()
    store, _, _ = install_runtime(monkeypatch, redis, settings=settings)
    user = api_client.agent_user  # type: ignore[attr-defined]
    conversation_id = uuid4()
    token = uuid4().hex
    await store.acquire_lock(
        user_id=user.id,
        conversation_id=conversation_id,
        token=token,
    )

    response = await api_client.post(
        "/api/v1/agent/chat",
        json={"message": "hello", "conversation_id": str(conversation_id)},
    )

    assert response.status_code == 409
    await store.release_lock(
        user_id=user.id,
        conversation_id=conversation_id,
        token=token,
    )


async def test_rate_limit_returns_429(
    api_client: AsyncClient,
    redis: Redis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = make_settings(agent_rate_limit_per_minute=1)
    install_runtime(monkeypatch, redis, settings=settings)

    first = await api_client.post("/api/v1/agent/chat", json={"message": "one"})
    second = await api_client.post("/api/v1/agent/chat", json={"message": "two"})

    assert first.status_code == 200, first.text
    assert second.status_code == 429
    assert second.headers.get("Retry-After")


async def test_rag_failure_returns_503(
    api_client: AsyncClient,
    redis: Redis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = make_settings()
    retrieval = FakeRetrieval()
    retrieval.fail = True
    install_runtime(
        monkeypatch,
        redis,
        settings=settings,
        llm=FakeLLM(["KNOWLEDGE"]),
        retrieval=retrieval,
    )

    response = await api_client.post(
        "/api/v1/agent/chat",
        json={"message": "退款条件是什么？"},
    )

    assert response.status_code == 503
    assert response.json()["code"] == "RAG_RETRIEVAL_UNAVAILABLE"


async def test_timeout_returns_504(
    api_client: AsyncClient,
    redis: Redis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class SlowLLM(FakeLLM):
        async def generate(self, **kwargs):  # type: ignore[override]
            await asyncio.sleep(3)
            return await super().generate(**kwargs)  # type: ignore[arg-type]

    settings = make_settings(agent_max_execution_seconds=1)
    install_runtime(
        monkeypatch,
        redis,
        settings=settings,
        llm=SlowLLM(["GENERAL", "late"]),
    )

    response = await api_client.post("/api/v1/agent/chat", json={"message": "slow"})

    assert response.status_code == 504
    assert response.json()["code"] == "AGENT_EXECUTION_TIMEOUT"


async def test_pending_action_is_returned_by_chat_api(
    api_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conversation_id = uuid4()
    now = datetime.now(UTC)

    class FakeRuntime:
        async def chat(self, **kwargs):
            return ChatResult(
                conversation_id=conversation_id,
                message_id=uuid4(),
                answer="请确认取消订单。",
                sources=[],
                created_at=now,
                pending_action={
                    "confirmation_id": "confirmation-1",
                    "nonce": "nonce-1",
                    "conversation_id": str(conversation_id),
                    "action_type": "CANCEL_ORDER",
                    "title": "取消订单",
                    "resource_no": "ORD-1",
                    "effect": "释放库存",
                    "summary": "取消订单 ORD-1",
                    "expires_at": now.isoformat(),
                },
            )

    monkeypatch.setattr(agent_api, "AgentRuntime", lambda **kwargs: FakeRuntime())

    response = await api_client.post(
        "/api/v1/agent/chat",
        json={"message": "取消订单"},
    )

    assert response.status_code == 200, response.text
    pending = response.json()["pending_action"]
    assert pending["confirmation_id"] == "confirmation-1"
    assert pending["conversation_id"] == str(conversation_id)
    assert pending["action_type"] == "CANCEL_ORDER"
