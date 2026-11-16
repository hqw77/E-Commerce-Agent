"""Real MySQL/Redis integration tests for Agent business tools."""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from app.api.dependencies import get_current_user
from app.core.config import get_settings
from app.db.redis import redis_client
from app.db.session import AsyncSessionLocal, get_db
from app.main import app
from app.models.after_sale import AfterSale
from app.models.category import Category
from app.models.inventory import Inventory
from app.models.inventory_transaction import InventoryTransaction
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.product import Product
from app.models.sku import Sku
from app.models.user import User
from app.schemas.order import OrderCreateRequest
from app.services.order import OrderService
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from sqlalchemy import delete, select

from agent.conversation import ConversationStore
from agent.llm import ToolCall
from agent.runtime import AgentRuntime
from agent.tests.fakes import FakeLLM, FakeRetrieval
from agent.tools import TOOL_REGISTRY
from agent.tools.confirmation import ConfirmationService, ConfirmationStore
from agent.tools.context import ToolContext
from agent.tools.errors import (
    AgentConfirmationExpiredError,
    AgentConfirmationMismatchError,
    AgentToolError,
)
from agent.tools.executor import ToolExecutor

pytestmark = pytest.mark.asyncio(loop_scope="module")


@pytest_asyncio.fixture(scope="module", autouse=True, loop_scope="module")
async def _reset_global_redis_pool():
    await redis_client.connection_pool.disconnect()
    yield
    await redis_client.connection_pool.disconnect()


PREFIX = "t7tool"


def _hash(attributes: dict[str, str]) -> str:
    return hashlib.sha256(
        json.dumps(attributes, sort_keys=True).encode("utf-8")
    ).hexdigest()


@pytest_asyncio.fixture(loop_scope="module")
async def redis() -> Redis:
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
async def seed() -> dict:
    async with AsyncSessionLocal() as session:
        user = User(
            email=f"{PREFIX}-{uuid4().hex}@example.com",
            password_hash="x",
            is_active=True,
            is_admin=False,
        )
        other = User(
            email=f"{PREFIX}-other-{uuid4().hex}@example.com",
            password_hash="x",
            is_active=True,
            is_admin=False,
        )
        category = Category(name=f"{PREFIX}-cat-{uuid4().hex[:8]}")
        session.add_all([user, other, category])
        await session.commit()
        await session.refresh(user)
        await session.refresh(other)
        await session.refresh(category)

        product = Product(
            product_no=f"{PREFIX.upper()}{uuid4().hex[:8].upper()}",
            category_id=category.id,
            name="Agent test product",
            description="test",
            status="ACTIVE",
            published_at=datetime.now(UTC).replace(tzinfo=None),
        )
        session.add(product)
        await session.commit()
        await session.refresh(product)

        sku = Sku(
            product_id=product.id,
            sku_code=f"{PREFIX.upper()}S{uuid4().hex[:8].upper()}",
            attributes={"color": "black"},
            attributes_hash=_hash({"color": "black"}),
            price=Decimal("19.90"),
            status="ACTIVE",
        )
        session.add(sku)
        await session.commit()
        await session.refresh(sku)
        session.add(
            Inventory(
                sku_id=sku.id,
                total_quantity=10,
                reserved_quantity=0,
            )
        )
        await session.commit()

        user_snapshot = SimpleNamespace(
            id=user.id,
            email=user.email,
            is_active=True,
            is_admin=False,
        )
        other_snapshot = SimpleNamespace(
            id=other.id,
            email=other.email,
            is_active=True,
            is_admin=False,
        )
        product_no = product.product_no
        product_id = product.id
        category_id = category.id
        sku_code = sku.sku_code
        sku_id = sku.id
        user_id = user.id
        other_id = other.id

    try:
        yield {
            "user": user_snapshot,
            "other": other_snapshot,
            "user_id": user_id,
            "other_id": other_id,
            "product_no": product_no,
            "sku_code": sku_code,
            "sku_id": sku_id,
            "product_id": product_id,
            "category_id": category_id,
        }
    finally:
        async with AsyncSessionLocal() as session:
            order_ids = select(Order.id).where(
                Order.user_id.in_([user_id, other_id])
            )
            await session.execute(
                delete(AfterSale).where(AfterSale.user_id.in_([user_id, other_id]))
            )
            await session.execute(
                delete(OrderItem).where(OrderItem.order_id.in_(order_ids))
            )
            await session.execute(
                delete(Order).where(Order.user_id.in_([user_id, other_id]))
            )
            await session.execute(
                delete(InventoryTransaction).where(
                    InventoryTransaction.sku_id == sku_id
                )
            )
            await session.execute(
                delete(Inventory).where(Inventory.sku_id == sku_id)
            )
            await session.execute(delete(Sku).where(Sku.id == sku_id))
            await session.execute(delete(Product).where(Product.id == product_id))
            await session.execute(delete(Category).where(Category.id == category_id))
            await session.execute(delete(User).where(User.id.in_([user_id, other_id])))
            await session.commit()


async def make_order(seed: dict, *, quantity: int = 2) -> tuple[int, str]:
    async with AsyncSessionLocal() as session:
        service = OrderService(session)
        order = await service.create_order(
            user_id=seed["user_id"],
            request=OrderCreateRequest(
                items=[{"sku_code": seed["sku_code"], "quantity": quantity}],
                receiver_name="Agent User",
                receiver_phone="13800000000",
                receiver_address="Shanghai",
                idempotency_key=f"t7-{uuid4().hex}",
            ),
        )
        return order.id, order.order_no


async def make_tool_context(
    seed: dict,
    redis: Redis,
    *,
    user: object | None = None,
) -> ToolContext:
    settings = get_settings()
    return ToolContext(
        user=(user or seed["user"]),  # type: ignore[arg-type]
        session=AsyncSessionLocal(),
        settings=settings,
        conversation_id=uuid4(),
        confirmation_store=ConfirmationStore(settings, redis=redis),
    )


async def execute_tool(
    seed: dict,
    redis: Redis,
    name: str,
    args: dict,
    *,
    user: object | None = None,
):
    context = await make_tool_context(seed, redis, user=user)
    try:
        executor = ToolExecutor(TOOL_REGISTRY, max_calls=4)
        return await executor.execute(name, args, context)
    finally:
        await context.session.close()


async def test_read_tools_use_services_and_hide_internal_ids(seed, redis) -> None:
    search = await execute_tool(
        seed,
        redis,
        "search_products",
        {"query": "Agent test", "page": 1, "page_size": 10},
    )
    assert search.ok
    assert search.data["items"]
    assert "id" not in search.data["items"][0]

    product = await execute_tool(
        seed,
        redis,
        "get_product_detail",
        {"product_no": seed["product_no"]},
    )
    assert product.ok
    assert product.data["product_no"] == seed["product_no"]
    assert "id" not in product.data

    sku = await execute_tool(
        seed,
        redis,
        "get_sku_detail",
        {"sku_code": seed["sku_code"]},
    )
    assert sku.ok
    assert sku.data["sku_code"] == seed["sku_code"]
    assert "id" not in sku.data

    inventory = await execute_tool(
        seed,
        redis,
        "check_sku_inventory",
        {"sku_code": seed["sku_code"]},
    )
    assert inventory.ok
    assert inventory.data["available_quantity"] >= 0

    _order_id, order_no = await make_order(seed)
    order = await execute_tool(seed, redis, "get_my_order", {"order_no": order_no})
    assert order.ok
    assert order.data["order_no"] == order_no
    assert "id" not in order.data
    assert all("id" not in item for item in order.data["items"])

    foreign = await execute_tool(
        seed,
        redis,
        "get_my_order",
        {"order_no": order_no},
        user=seed["other"],
    )
    assert not foreign.ok
    assert foreign.error_code == "ORDER_NOT_FOUND"


async def test_prepare_cancel_is_side_effect_free_and_confirm_cancels(seed, redis) -> None:
    _order_id, order_no = await make_order(seed, quantity=2)
    prepared = await execute_tool(
        seed,
        redis,
        "prepare_cancel_order",
        {"order_no": order_no, "reason": "test"},
    )
    assert prepared.ok
    assert prepared.pending_action
    assert prepared.pending_action["confirmation_id"]

    async with AsyncSessionLocal() as session:
        order = (
            await session.execute(select(Order).where(Order.order_no == order_no))
        ).scalar_one()
        assert order.status == "PENDING_PAYMENT"
        inventory = (
            await session.execute(select(Inventory).where(Inventory.sku_id == seed["sku_id"]))
        ).scalar_one()
        assert inventory.reserved_quantity == 2

    service = ConfirmationService(
        session=AsyncSessionLocal(),
        user=seed["user"],  # type: ignore[arg-type]
        store=ConfirmationStore(get_settings(), redis=redis),
    )
    try:
        confirmed = await service.confirm(
            confirmation_id=prepared.pending_action["confirmation_id"],
            conversation_id=prepared.pending_action["conversation_id"],
            nonce=prepared.pending_action["nonce"],
        )
    finally:
        await service.session.close()

    assert confirmed.status == "CANCELLED"
    async with AsyncSessionLocal() as session:
        order = (
            await session.execute(select(Order).where(Order.order_no == order_no))
        ).scalar_one()
        assert order.status == "CANCELLED"
        inventory = (
            await session.execute(select(Inventory).where(Inventory.sku_id == seed["sku_id"]))
        ).scalar_one()
        assert inventory.reserved_quantity == 0
        releases = (
            await session.execute(
                select(InventoryTransaction).where(
                    InventoryTransaction.transaction_type == "RELEASE",
                    InventoryTransaction.sku_id == seed["sku_id"],
                )
            )
        ).scalars().all()
        assert releases


async def test_prepare_after_sale_is_side_effect_free_and_confirm_creates_pending(seed, redis) -> None:
    _order_id, order_no = await make_order(seed, quantity=1)
    async with AsyncSessionLocal() as session:
        order = (
            await session.execute(select(Order).where(Order.order_no == order_no))
        ).scalar_one()
        order.status = "PAID"
        order.payment_status = "PAID"
        order.fulfillment_status = "UNSHIPPED"
        order.paid_at = datetime.now(UTC).replace(tzinfo=None)
        await session.commit()

    prepared = await execute_tool(
        seed,
        redis,
        "prepare_create_after_sales",
        {
            "order_no": order_no,
            "sku_code": seed["sku_code"],
            "type": "REFUND_ONLY",
            "reason": "not needed",
        },
    )
    assert prepared.ok
    assert prepared.pending_action

    async with AsyncSessionLocal() as session:
        count = len((await session.execute(select(AfterSale))).scalars().all())
        assert count == 0

    service = ConfirmationService(
        session=AsyncSessionLocal(),
        user=seed["user"],  # type: ignore[arg-type]
        store=ConfirmationStore(get_settings(), redis=redis),
    )
    try:
        confirmed = await service.confirm(
            confirmation_id=prepared.pending_action["confirmation_id"],
            conversation_id=prepared.pending_action["conversation_id"],
            nonce=prepared.pending_action["nonce"],
        )
    finally:
        await service.session.close()

    assert confirmed.status == "PENDING_REVIEW"
    assert confirmed.after_sales_no
    async with AsyncSessionLocal() as session:
        after_sale = (
            await session.execute(
                select(AfterSale).where(
                    AfterSale.after_sales_no == confirmed.after_sales_no
                )
            )
        ).scalar_one()
        assert after_sale.status == "PENDING_REVIEW"

    queried = await execute_tool(
        seed,
        redis,
        "get_my_after_sales",
        {"after_sales_no": confirmed.after_sales_no},
    )
    assert queried.ok
    assert queried.data["status"] == "PENDING_REVIEW"
    assert "id" not in queried.data

    listed = await execute_tool(
        seed,
        redis,
        "list_my_after_sales",
        {"order_no": order_no, "page": 1, "page_size": 10},
    )
    assert listed.ok
    assert listed.data["items"]
    assert "id" not in listed.data["items"][0]


async def test_confirmation_api_is_one_time(seed, redis) -> None:
    _order_id, order_no = await make_order(seed, quantity=1)
    prepared = await execute_tool(
        seed,
        redis,
        "prepare_cancel_order",
        {"order_no": order_no, "reason": "api confirmation"},
    )
    assert prepared.pending_action

    async def override_get_db():
        async with AsyncSessionLocal() as session:
            yield session

    async def fake_user():
        return seed["user"]

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = fake_user
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            first = await client.post(
                f"/api/v1/agent/actions/{prepared.pending_action['confirmation_id']}/confirm",
                json={
                    "conversation_id": prepared.pending_action["conversation_id"],
                    "nonce": prepared.pending_action["nonce"],
                },
            )
            second = await client.post(
                f"/api/v1/agent/actions/{prepared.pending_action['confirmation_id']}/confirm",
                json={
                    "conversation_id": prepared.pending_action["conversation_id"],
                    "nonce": prepared.pending_action["nonce"],
                },
            )
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)

    assert first.status_code == 200, first.text
    assert first.json()["success"] is True
    assert second.status_code in {404, 409}
    async with AsyncSessionLocal() as session:
        order = (
            await session.execute(select(Order).where(Order.order_no == order_no))
        ).scalar_one()
        assert order.status == "CANCELLED"


async def test_agent_graph_calls_read_tool(seed, redis) -> None:
    _order_id, order_no = await make_order(seed, quantity=1)
    settings = get_settings()
    fake_llm = FakeLLM(
        ["", "订单当前处于待支付状态。"],
        tool_calls=[ToolCall(name="get_my_order", args={"order_no": order_no})],
    )
    session = AsyncSessionLocal()
    runtime = AgentRuntime(
        session,
        seed["user"],  # type: ignore[arg-type]
        settings,
        llm=fake_llm,
        retrieval=FakeRetrieval(),
        conversation_store=ConversationStore(settings, redis=redis),
        confirmation_store=ConfirmationStore(settings, redis=redis),
    )
    conversation_id = None
    try:
        result = await runtime.chat(message="查询我的订单")
        conversation_id = result.conversation_id
        assert "订单" in result.answer
        assert result.pending_action is None
        assert fake_llm.tool_planning_calls
        assert fake_llm.tool_planning_calls[0]["tools"]
    finally:
        await session.close()
        if conversation_id is not None:
            keys = [
                key
                async for key in redis.scan_iter(
                    f"agent:*:{seed['user_id']}:*"
                )
            ]
            if keys:
                await redis.delete(*keys)


async def test_agent_graph_prepare_has_no_side_effect(seed, redis) -> None:
    _order_id, order_no = await make_order(seed, quantity=1)
    settings = get_settings()
    fake_llm = FakeLLM(
        [],
        tool_calls=[
            ToolCall(
                name="prepare_cancel_order",
                args={"order_no": order_no, "reason": "agent prepare"},
            )
        ],
    )
    session = AsyncSessionLocal()
    runtime = AgentRuntime(
        session,
        seed["user"],  # type: ignore[arg-type]
        settings,
        llm=fake_llm,
        retrieval=FakeRetrieval(),
        conversation_store=ConversationStore(settings, redis=redis),
        confirmation_store=ConfirmationStore(settings, redis=redis),
    )
    conversation_id = None
    try:
        result = await runtime.chat(message="帮我取消订单")
        conversation_id = result.conversation_id
        assert result.pending_action is not None
        assert result.pending_action["action_type"] == "CANCEL_ORDER"
        assert "confirmation_id" in result.pending_action
        async with AsyncSessionLocal() as session2:
            order = (
                await session2.execute(
                    select(Order).where(Order.order_no == order_no)
                )
            ).scalar_one()
            assert order.status == "PENDING_PAYMENT"
    finally:
        await session.close()
        if conversation_id is not None:
            keys = [
                key
                async for key in redis.scan_iter(
                    f"agent:*:{seed['user_id']}:*"
                )
            ]
            if keys:
                await redis.delete(*keys)


async def test_confirmation_rejects_wrong_user_and_nonce(seed, redis) -> None:
    _order_id, order_no = await make_order(seed, quantity=1)
    prepared = await execute_tool(
        seed,
        redis,
        "prepare_cancel_order",
        {"order_no": order_no},
    )
    pending = prepared.pending_action
    assert pending is not None
    store = ConfirmationStore(get_settings(), redis=redis)

    wrong_user = ConfirmationService(
        session=AsyncSessionLocal(),
        user=seed["other"],  # type: ignore[arg-type]
        store=store,
    )
    try:
        with pytest.raises(AgentConfirmationMismatchError):
            await wrong_user.confirm(
                confirmation_id=pending["confirmation_id"],
                conversation_id=pending["conversation_id"],
                nonce=pending["nonce"],
            )
    finally:
        await wrong_user.session.close()

    wrong_nonce = ConfirmationService(
        session=AsyncSessionLocal(),
        user=seed["user"],  # type: ignore[arg-type]
        store=store,
    )
    try:
        with pytest.raises(AgentConfirmationMismatchError):
            await wrong_nonce.confirm(
                confirmation_id=pending["confirmation_id"],
                conversation_id=pending["conversation_id"],
                nonce="wrong-nonce",
            )
    finally:
        await wrong_nonce.session.close()

    correct = ConfirmationService(
        session=AsyncSessionLocal(),
        user=seed["user"],  # type: ignore[arg-type]
        store=store,
    )
    try:
        result = await correct.confirm(
            confirmation_id=pending["confirmation_id"],
            conversation_id=pending["conversation_id"],
            nonce=pending["nonce"],
        )
    finally:
        await correct.session.close()
    assert result.status == "CANCELLED"


async def test_confirmation_expiry_is_rejected(seed, redis) -> None:
    store = ConfirmationStore(get_settings(), redis=redis)
    offer = await store.create(
        user_id=seed["user_id"],
        conversation_id=uuid4(),
        operation="CANCEL_ORDER",
        tool_name="prepare_cancel_order",
        resource_no="ORD-EXPIRED",
        arguments={"order_no": "ORD-EXPIRED", "reason": None},
        summary="expired",
    )
    key = store.key(offer.confirmation_id)
    raw = await redis.get(key)
    assert raw is not None
    data = json.loads(raw)
    data["expires_at"] = int(time.time()) - 1
    await redis.set(key, json.dumps(data), ex=300)

    service = ConfirmationService(
        session=AsyncSessionLocal(),
        user=seed["user"],  # type: ignore[arg-type]
        store=store,
    )
    try:
        with pytest.raises(AgentConfirmationExpiredError):
            await service.confirm(
                confirmation_id=offer.confirmation_id,
                conversation_id=offer.conversation_id,
                nonce=offer.nonce,
            )
    finally:
        await service.session.close()


async def test_concurrent_confirm_only_one_executes(seed, redis) -> None:
    _order_id, order_no = await make_order(seed, quantity=1)
    prepared = await execute_tool(
        seed,
        redis,
        "prepare_cancel_order",
        {"order_no": order_no},
    )
    pending = prepared.pending_action
    assert pending is not None
    store = ConfirmationStore(get_settings(), redis=redis)

    async def attempt() -> object:
        service = ConfirmationService(
            session=AsyncSessionLocal(),
            user=seed["user"],  # type: ignore[arg-type]
            store=store,
        )
        try:
            return await service.confirm(
                confirmation_id=pending["confirmation_id"],
                conversation_id=pending["conversation_id"],
                nonce=pending["nonce"],
            )
        except AgentToolError as exc:
            return exc
        finally:
            await service.session.close()

    results = await asyncio.gather(attempt(), attempt())
    successes = [r for r in results if getattr(r, "status", None) == "CANCELLED"]
    failures = [r for r in results if isinstance(r, AgentToolError)]
    assert len(successes) == 1
    assert len(failures) == 1

