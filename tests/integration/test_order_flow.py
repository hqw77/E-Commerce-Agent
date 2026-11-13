import asyncio
import hashlib
import json
from datetime import timedelta
from types import SimpleNamespace
from typing import Annotated
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from fastapi import Depends
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.config import settings
from app.db.session import AsyncSessionLocal, get_db
from app.main import app
from app.models.after_sale import AfterSale
from app.models.category import Category
from app.models.inventory import Inventory
from app.models.inventory_transaction import InventoryTransaction
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.payment import Payment
from app.models.product import Product
from app.models.refund import Refund
from app.models.sku import Sku
from app.models.user import User
from app.services.alipay import AlipayClient
from app.utils.order import utc_now

PREFIX = "t4flow"


def _hash(attributes: dict[str, str]) -> str:
    return hashlib.sha256(
        json.dumps(attributes, sort_keys=True).encode("utf-8")
    ).hexdigest()


@pytest_asyncio.fixture
async def flow():
    async with AsyncSessionLocal() as session:
        user = User(
            email=f"{PREFIX}-{uuid4().hex}@example.com",
            password_hash="hashed",
            is_active=True,
            is_admin=False,
        )
        admin = User(
            email=f"{PREFIX}-admin-{uuid4().hex}@example.com",
            password_hash="hashed",
            is_active=True,
            is_admin=True,
        )
        category = Category(name=f"{PREFIX}-cat-{uuid4().hex[:8]}")
        session.add_all([user, admin, category])
        await session.commit()
        await session.refresh(user)
        await session.refresh(admin)
        await session.refresh(category)

        product = Product(
            product_no=f"{PREFIX.upper()}{uuid4().hex[:10].upper()}",
            category_id=category.id,
            name="Flow product",
            description="test",
            status="ACTIVE",
            published_at=utc_now(),
        )
        session.add(product)
        await session.commit()
        await session.refresh(product)

        sku = Sku(
            product_id=product.id,
            sku_code=f"{PREFIX.upper()}S{uuid4().hex[:8].upper()}",
            attributes={"color": "black"},
            attributes_hash=_hash({"color": "black"}),
            price="19.90",
            status="ACTIVE",
        )
        session.add(sku)
        await session.commit()
        await session.refresh(sku)

        inventory = Inventory(
            sku_id=sku.id,
            total_quantity=10,
            reserved_quantity=0,
        )
        session.add(inventory)
        await session.commit()

        user_snapshot = SimpleNamespace(
            id=user.id,
            email=user.email,
            is_active=True,
            is_admin=False,
        )
        admin_snapshot = SimpleNamespace(
            id=admin.id,
            email=admin.email,
            is_active=True,
            is_admin=True,
        )

    current: dict[str, SimpleNamespace | None] = {"user": user_snapshot}

    async def override_get_db():
        async with AsyncSessionLocal() as session:
            yield session

    async def fake_current_user(
        session: Annotated[AsyncSession, Depends(get_db)],
    ) -> SimpleNamespace:
        await session.execute(select(1))
        if current["user"] is None:
            from app.core.exceptions import AuthenticationException

            raise AuthenticationException()
        return current["user"]

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = fake_current_user
    transport = ASGITransport(app=app)

    try:
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            yield (
                client,
                {
                    "user": user_snapshot,
                    "admin": admin_snapshot,
                    "current": current,
                    "sku": sku,
                    "sku_code": sku.sku_code,
                },
            )
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)
        async with AsyncSessionLocal() as session:
            await session.execute(delete(Refund))
            await session.execute(delete(AfterSale))
            await session.execute(delete(OrderItem))
            await session.execute(delete(Payment))
            await session.execute(delete(Order))
            await session.execute(delete(InventoryTransaction))
            await session.execute(delete(Inventory))
            await session.execute(delete(Sku))
            await session.execute(delete(Product))
            await session.execute(delete(Category))
            await session.execute(delete(User))
            await session.commit()


def order_payload(sku_code: str, key: str, quantity: int = 2) -> dict:
    return {
        "items": [{"sku_code": sku_code, "quantity": quantity}],
        "receiver_name": "Test User",
        "receiver_phone": "13800000000",
        "receiver_address": "Shanghai",
        "customer_remark": None,
        "idempotency_key": key,
    }


async def _create_paid_order(flow, quantity: int = 1) -> str:
    client, state = flow
    created = await client.post(
        "/api/v1/orders",
        json=order_payload(state["sku_code"], f"key-{uuid4().hex}", quantity),
    )
    assert created.status_code == 201, created.text
    order_no = created.json()["order_no"]
    payment = await client.post(
        f"/api/v1/orders/{order_no}/payments",
        json={"channel": "MOCK"},
    )
    assert payment.status_code == 200, payment.text
    payment_no = payment.json()["payment_no"]
    paid = await client.post(f"/api/v1/payments/{payment_no}/mock-success")
    assert paid.status_code == 200, paid.text
    assert paid.json()["status"] == "SUCCESS"
    return order_no


async def _advance_to_delivered(flow, order_no: str) -> None:
    client, state = flow
    state["current"]["user"] = state["admin"]
    for action in ("ship", "deliver"):
        payload = (
            {"shipping_carrier": "SF", "tracking_no": "SF123"}
            if action == "ship"
            else None
        )
        response = await client.post(
            f"/api/v1/admin/orders/{order_no}/{action}",
            json=payload,
        )
        assert response.status_code == 200, response.text
    state["current"]["user"] = state["user"]


@pytest.mark.asyncio
async def test_order_create_idempotency_cancel_and_reservation(flow):
    client, state = flow
    key = f"idem-{uuid4().hex}"
    payload = order_payload(state["sku_code"], key, 2)

    first = await client.post("/api/v1/orders", json=payload)
    assert first.status_code == 201, first.text
    body = first.json()
    assert body["total_amount"] == "39.80"
    assert body["status"] == "PENDING_PAYMENT"
    assert body["items"][0]["quantity"] == 2
    assert body["items"][0]["unit_price"] == "19.90"

    async with AsyncSessionLocal() as session:
        inventory = (
            await session.execute(
                select(Inventory).where(Inventory.sku_id == state["sku"].id)
            )
        ).scalar_one()
        assert inventory.reserved_quantity == 2

    same = await client.post("/api/v1/orders", json=payload)
    assert same.status_code == 201
    assert same.json()["order_no"] == body["order_no"]

    conflict_payload = order_payload(state["sku_code"], key, 1)
    conflict = await client.post("/api/v1/orders", json=conflict_payload)
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "IDEMPOTENCY_KEY_CONFLICT"

    cancelled = await client.post(f"/api/v1/orders/{body['order_no']}/cancel")
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "CANCELLED"

    async with AsyncSessionLocal() as session:
        inventory = (
            await session.execute(
                select(Inventory).where(Inventory.sku_id == state["sku"].id)
            )
        ).scalar_one()
        assert inventory.reserved_quantity == 0


@pytest.mark.asyncio
async def test_payment_success_is_idempotent_and_deducts_stock(flow):
    client, state = flow
    order_no = await _create_paid_order(flow, 2)

    async with AsyncSessionLocal() as session:
        inventory = (
            await session.execute(
                select(Inventory).where(Inventory.sku_id == state["sku"].id)
            )
        ).scalar_one()
        assert inventory.total_quantity == 8
        assert inventory.reserved_quantity == 0
        order = (
            await session.execute(select(Order).where(Order.order_no == order_no))
        ).scalar_one()
        assert order.status == "PAID"
        payment = (
            await session.execute(select(Payment).where(Payment.order_id == order.id))
        ).scalar_one()
        payment_no = payment.payment_no

    duplicate = await client.post(f"/api/v1/payments/{payment_no}/mock-success")
    assert duplicate.status_code == 200
    async with AsyncSessionLocal() as session:
        inventory = (
            await session.execute(
                select(Inventory).where(Inventory.sku_id == state["sku"].id)
            )
        ).scalar_one()
        assert inventory.total_quantity == 8


@pytest.mark.asyncio
async def test_admin_fulfillment_and_permissions(flow):
    client, state = flow
    order_no = await _create_paid_order(flow, 1)

    denied = await client.get(f"/api/v1/admin/orders/{order_no}")
    assert denied.status_code == 403

    await _advance_to_delivered(flow, order_no)
    state["current"]["user"] = state["admin"]
    completed = await client.post(f"/api/v1/admin/orders/{order_no}/complete")
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "COMPLETED"
    assert completed.json()["fulfillment_status"] == "COMPLETED"


@pytest.mark.asyncio
async def test_refund_only_after_sales_restocks_unshipped_order(flow):
    client, state = flow
    order_no = await _create_paid_order(flow, 1)
    applied = await client.post(
        f"/api/v1/orders/{order_no}/after-sales",
        json={
            "sku_code": state["sku_code"],
            "type": "REFUND_ONLY",
            "reason": "not needed",
            "description": "test",
            "idempotency_key": f"as-{uuid4().hex}",
        },
    )
    assert applied.status_code == 201, applied.text
    after_sales_no = applied.json()["after_sales_no"]

    state["current"]["user"] = state["admin"]
    approved = await client.post(
        f"/api/v1/admin/after-sales/{after_sales_no}/approve",
        json={"review_note": "ok"},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "COMPLETED"

    async with AsyncSessionLocal() as session:
        inventory = (
            await session.execute(
                select(Inventory).where(Inventory.sku_id == state["sku"].id)
            )
        ).scalar_one()
        assert inventory.total_quantity == 10
        order = (
            await session.execute(select(Order).where(Order.order_no == order_no))
        ).scalar_one()
        assert order.payment_status == "REFUNDED"


@pytest.mark.asyncio
async def test_return_refund_flow(flow):
    client, state = flow
    order_no = await _create_paid_order(flow, 1)
    await _advance_to_delivered(flow, order_no)

    applied = await client.post(
        f"/api/v1/orders/{order_no}/after-sales",
        json={
            "sku_code": state["sku_code"],
            "type": "RETURN_REFUND",
            "reason": "return",
            "idempotency_key": f"as-{uuid4().hex}",
        },
    )
    assert applied.status_code == 201, applied.text
    after_sales_no = applied.json()["after_sales_no"]

    state["current"]["user"] = state["admin"]
    approved = await client.post(
        f"/api/v1/admin/after-sales/{after_sales_no}/approve",
        json={"review_note": "ok"},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "WAITING_RETURN"

    state["current"]["user"] = state["user"]
    shipped = await client.post(
        f"/api/v1/after-sales/{after_sales_no}/return-shipment",
        json={"return_carrier": "SF", "return_tracking_no": "RET123"},
    )
    assert shipped.status_code == 200, shipped.text
    assert shipped.json()["status"] == "RETURN_SHIPPED"

    state["current"]["user"] = state["admin"]
    received = await client.post(f"/api/v1/admin/after-sales/{after_sales_no}/receive")
    assert received.status_code == 200, received.text
    assert received.json()["status"] == "COMPLETED"

    async with AsyncSessionLocal() as session:
        inventory = (
            await session.execute(
                select(Inventory).where(Inventory.sku_id == state["sku"].id)
            )
        ).scalar_one()
        assert inventory.total_quantity == 10


@pytest.mark.asyncio
async def test_exchange_flow(flow):
    client, state = flow
    order_no = await _create_paid_order(flow, 1)
    await _advance_to_delivered(flow, order_no)

    applied = await client.post(
        f"/api/v1/orders/{order_no}/after-sales",
        json={
            "sku_code": state["sku_code"],
            "type": "EXCHANGE",
            "reason": "size",
            "idempotency_key": f"as-{uuid4().hex}",
        },
    )
    assert applied.status_code == 201, applied.text
    after_sales_no = applied.json()["after_sales_no"]

    state["current"]["user"] = state["admin"]
    approved = await client.post(
        f"/api/v1/admin/after-sales/{after_sales_no}/approve",
        json={"review_note": "ok"},
    )
    assert approved.status_code == 200, approved.text

    state["current"]["user"] = state["user"]
    shipped = await client.post(
        f"/api/v1/after-sales/{after_sales_no}/return-shipment",
        json={"return_carrier": "SF", "return_tracking_no": "RET123"},
    )
    assert shipped.status_code == 200, shipped.text

    state["current"]["user"] = state["admin"]
    received = await client.post(f"/api/v1/admin/after-sales/{after_sales_no}/receive")
    assert received.status_code == 200, received.text
    assert received.json()["status"] == "RECEIVED"

    completed = await client.post(
        f"/api/v1/admin/after-sales/{after_sales_no}/complete-exchange",
        json={
            "replacement_carrier": "SF",
            "replacement_tracking_no": "REP123",
        },
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "COMPLETED"

    async with AsyncSessionLocal() as session:
        inventory = (
            await session.execute(
                select(Inventory).where(Inventory.sku_id == state["sku"].id)
            )
        ).scalar_one()
        assert inventory.total_quantity == 9


@pytest.mark.asyncio
async def test_order_stock_and_status_guards(flow):
    client, state = flow
    insufficient = await client.post(
        "/api/v1/orders",
        json=order_payload(state["sku_code"], f"stock-{uuid4().hex}", 11),
    )
    assert insufficient.status_code == 409
    assert insufficient.json()["code"] == "INSUFFICIENT_STOCK"

    invalid_sku = await client.post(
        "/api/v1/orders",
        json=order_payload("MISSING-SKU", f"sku-{uuid4().hex}", 1),
    )
    assert invalid_sku.status_code == 409
    assert invalid_sku.json()["code"] == "SKU_NOT_AVAILABLE"

    paid_order = await _create_paid_order(flow, 1)
    cancel_paid = await client.post(f"/api/v1/orders/{paid_order}/cancel")
    assert cancel_paid.status_code == 409
    assert cancel_paid.json()["code"] == "ORDER_STATUS_CONFLICT"


@pytest.mark.asyncio
async def test_after_sales_invalid_state_and_cross_user_access(flow):
    client, state = flow
    order_no = await _create_paid_order(flow, 1)
    applied = await client.post(
        f"/api/v1/orders/{order_no}/after-sales",
        json={
            "sku_code": state["sku_code"],
            "type": "REFUND_ONLY",
            "reason": "test",
            "idempotency_key": f"as-invalid-{uuid4().hex}",
        },
    )
    assert applied.status_code == 201
    after_sales_no = applied.json()["after_sales_no"]

    wrong_state = await client.post(
        f"/api/v1/after-sales/{after_sales_no}/return-shipment",
        json={"return_carrier": "SF", "return_tracking_no": "RET"},
    )
    assert wrong_state.status_code == 409
    assert wrong_state.json()["code"] == "RETURN_NOT_ALLOWED"

    state["current"]["user"] = SimpleNamespace(
        id=state["admin"].id + 2000,
        email="other-as@example.com",
        is_active=True,
        is_admin=False,
    )
    other = await client.get(f"/api/v1/after-sales/{after_sales_no}")
    assert other.status_code == 404

    state["current"]["user"] = state["user"]
    admin_denied = await client.get("/api/v1/admin/after-sales")
    assert admin_denied.status_code == 403


@pytest.mark.asyncio
async def test_payment_callback_and_timeout_close_race(flow):
    client, state = flow
    created = await client.post(
        "/api/v1/orders",
        json=order_payload(state["sku_code"], f"race-{uuid4().hex}", 1),
    )
    order_no = created.json()["order_no"]
    payment = await client.post(
        f"/api/v1/orders/{order_no}/payments",
        json={"channel": "MOCK"},
    )
    payment_no = payment.json()["payment_no"]
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(Order)
            .where(Order.order_no == order_no)
            .values(expires_at=utc_now() - timedelta(minutes=1))
        )
        await session.commit()

    state["user"].is_admin = True

    async def pay():
        return await client.post(f"/api/v1/payments/{payment_no}/mock-success")

    async def close():
        return await client.post("/api/v1/admin/orders/close-expired")

    paid, closed = await asyncio.gather(pay(), close())
    assert paid.status_code == 200, paid.text
    assert closed.status_code == 200, closed.text

    async with AsyncSessionLocal() as session:
        order = (
            await session.execute(select(Order).where(Order.order_no == order_no))
        ).scalar_one()
        payment_row = (
            await session.execute(
                select(Payment).where(Payment.payment_no == payment_no)
            )
        ).scalar_one()
        inventory = (
            await session.execute(
                select(Inventory).where(Inventory.sku_id == state["sku"].id)
            )
        ).scalar_one()
        assert order.status == "CLOSED"
        assert payment_row.status == "SUCCESS"
        assert payment_row.exception_reason == "LATE_PAYMENT"
        assert inventory.total_quantity == 10
        assert inventory.reserved_quantity == 0


@pytest.mark.asyncio
async def test_user_cannot_access_other_order(flow):
    client, state = flow
    order_no = await _create_paid_order(flow, 1)
    state["current"]["user"] = SimpleNamespace(
        id=state["admin"].id + 1000,
        email="other@example.com",
        is_active=True,
        is_admin=False,
    )
    response = await client.get(f"/api/v1/orders/{order_no}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_late_payment_and_manual_refund(flow):
    client, state = flow
    await _create_paid_order(flow, 1)
    state["current"]["user"] = state["user"]
    # The helper paid the order; create a separate order and cancel it before payment.
    created = await client.post(
        "/api/v1/orders",
        json=order_payload(state["sku_code"], f"late-{uuid4().hex}", 1),
    )
    late_order_no = created.json()["order_no"]
    payment = await client.post(
        f"/api/v1/orders/{late_order_no}/payments",
        json={"channel": "MOCK"},
    )
    payment_no = payment.json()["payment_no"]
    await client.post(f"/api/v1/orders/{late_order_no}/cancel")

    late = await client.post(f"/api/v1/payments/{payment_no}/mock-success")
    assert late.status_code == 200, late.text
    assert late.json()["late_payment"] is True
    assert late.json()["order_status"] == "CANCELLED"
    assert late.json()["order_payment_status"] == "PAID"

    async with AsyncSessionLocal() as session:
        inventory = (
            await session.execute(
                select(Inventory).where(Inventory.sku_id == state["sku"].id)
            )
        ).scalar_one()
        assert inventory.total_quantity == 9
        assert inventory.reserved_quantity == 0

    state["current"]["user"] = state["admin"]
    refund = await client.post(
        "/api/v1/admin/refunds",
        json={
            "payment_no": payment_no,
            "amount": "19.90",
            "reason": "LATE_PAYMENT",
            "idempotency_key": f"late-refund-{uuid4().hex}",
        },
    )
    assert refund.status_code == 201, refund.text
    assert refund.json()["status"] == "SUCCESS"

    async with AsyncSessionLocal() as session:
        order = (
            await session.execute(select(Order).where(Order.order_no == late_order_no))
        ).scalar_one()
        assert order.payment_status == "REFUNDED"
        inventory = (
            await session.execute(
                select(Inventory).where(Inventory.sku_id == state["sku"].id)
            )
        ).scalar_one()
        assert inventory.total_quantity == 9


@pytest.mark.asyncio
async def test_expired_payment_callback_releases_reservation(flow):
    client, state = flow
    created = await client.post(
        "/api/v1/orders",
        json=order_payload(state["sku_code"], f"expired-{uuid4().hex}", 1),
    )
    order_no = created.json()["order_no"]
    payment = await client.post(
        f"/api/v1/orders/{order_no}/payments",
        json={"channel": "MOCK"},
    )
    payment_no = payment.json()["payment_no"]

    async with AsyncSessionLocal() as session:
        await session.execute(
            update(Order)
            .where(Order.order_no == order_no)
            .values(expires_at=utc_now() - timedelta(minutes=1))
        )
        await session.commit()

    paid = await client.post(f"/api/v1/payments/{payment_no}/mock-success")
    assert paid.status_code == 200, paid.text
    assert paid.json()["late_payment"] is True
    assert paid.json()["order_status"] == "CLOSED"

    async with AsyncSessionLocal() as session:
        inventory = (
            await session.execute(
                select(Inventory).where(Inventory.sku_id == state["sku"].id)
            )
        ).scalar_one()
        assert inventory.total_quantity == 10
        assert inventory.reserved_quantity == 0
        order = (
            await session.execute(select(Order).where(Order.order_no == order_no))
        ).scalar_one()
        assert order.payment_status == "PAID"


@pytest.mark.asyncio
async def test_close_expired_orders(flow):
    client, state = flow
    created = await client.post(
        "/api/v1/orders",
        json=order_payload(state["sku_code"], f"close-{uuid4().hex}", 1),
    )
    order_no = created.json()["order_no"]
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(Order)
            .where(Order.order_no == order_no)
            .values(expires_at=utc_now() - timedelta(minutes=1))
        )
        await session.commit()

    state["current"]["user"] = state["admin"]
    closed = await client.post("/api/v1/admin/orders/close-expired")
    assert closed.status_code == 200, closed.text
    assert closed.json()["closed_count"] >= 1

    async with AsyncSessionLocal() as session:
        order = (
            await session.execute(select(Order).where(Order.order_no == order_no))
        ).scalar_one()
        assert order.status == "CLOSED"
        inventory = (
            await session.execute(
                select(Inventory).where(Inventory.sku_id == state["sku"].id)
            )
        ).scalar_one()
        assert inventory.reserved_quantity == 0


@pytest.mark.asyncio
async def test_refund_amount_limit_and_duplicate_refund(flow):
    client, state = flow
    order_no = await _create_paid_order(flow, 1)
    payment = await client.get("/api/v1/payments")
    payment_no = payment.json()["items"][0]["payment_no"]

    state["current"]["user"] = state["admin"]
    too_much = await client.post(
        "/api/v1/admin/refunds",
        json={
            "payment_no": payment_no,
            "amount": "20.00",
            "reason": "test",
            "idempotency_key": f"r-too-{uuid4().hex}",
        },
    )
    assert too_much.status_code == 409
    assert too_much.json()["code"] == "REFUND_AMOUNT_EXCEEDED"

    first_key = f"r-1-{uuid4().hex}"
    first = await client.post(
        "/api/v1/admin/refunds",
        json={
            "payment_no": payment_no,
            "amount": "10.00",
            "reason": "partial",
            "idempotency_key": first_key,
        },
    )
    assert first.status_code == 201, first.text
    assert first.json()["status"] == "SUCCESS"

    duplicate = await client.post(
        "/api/v1/admin/refunds",
        json={
            "payment_no": payment_no,
            "amount": "10.00",
            "reason": "partial",
            "idempotency_key": first_key,
        },
    )
    assert duplicate.status_code == 201
    assert duplicate.json()["refund_no"] == first.json()["refund_no"]

    second = await client.post(
        "/api/v1/admin/refunds",
        json={
            "payment_no": payment_no,
            "amount": "9.90",
            "reason": "rest",
            "idempotency_key": f"r-2-{uuid4().hex}",
        },
    )
    assert second.status_code == 201, second.text
    assert second.json()["status"] == "SUCCESS"

    async with AsyncSessionLocal() as session:
        order = (
            await session.execute(select(Order).where(Order.order_no == order_no))
        ).scalar_one()
        assert order.payment_status == "REFUNDED"


@pytest.mark.asyncio
async def test_payment_creation_guards_and_failed_payment(flow):
    client, state = flow
    created = await client.post(
        "/api/v1/orders",
        json=order_payload(state["sku_code"], f"payguard-{uuid4().hex}", 1),
    )
    order_no = created.json()["order_no"]
    mock = await client.post(
        f"/api/v1/orders/{order_no}/payments",
        json={"channel": "MOCK"},
    )
    assert mock.status_code == 200
    conflict = await client.post(
        f"/api/v1/orders/{order_no}/payments",
        json={"channel": "ALIPAY"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "PAYMENT_CHANNEL_CONFLICT"

    payment_no = mock.json()["payment_no"]
    failed = await client.post(f"/api/v1/payments/{payment_no}/mock-fail")
    assert failed.status_code == 200
    retry = await client.post(
        f"/api/v1/orders/{order_no}/payments",
        json={"channel": "MOCK"},
    )
    assert retry.status_code == 409
    assert retry.json()["code"] == "PAYMENT_NOT_RETRYABLE"

    cancelled = await client.post(f"/api/v1/orders/{order_no}/cancel")
    assert cancelled.status_code == 200
    after_cancel = await client.post(
        f"/api/v1/orders/{order_no}/payments",
        json={"channel": "MOCK"},
    )
    assert after_cancel.status_code == 409
    assert after_cancel.json()["code"] == "ORDER_STATUS_CONFLICT"


@pytest.mark.asyncio
async def test_order_concurrent_idempotency(flow):
    client, state = flow
    key = f"concurrent-{uuid4().hex}"
    payload = order_payload(state["sku_code"], key, 2)

    async def create():
        return await client.post("/api/v1/orders", json=payload)

    first, second = await asyncio.gather(create(), create())
    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert first.json()["order_no"] == second.json()["order_no"]

    async with AsyncSessionLocal() as session:
        inventory = (
            await session.execute(
                select(Inventory).where(Inventory.sku_id == state["sku"].id)
            )
        ).scalar_one()
        assert inventory.reserved_quantity == 2


@pytest.mark.asyncio
async def test_after_sales_window_and_state_guards(flow):
    client, state = flow
    order_no = await _create_paid_order(flow, 1)
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(Order)
            .where(Order.order_no == order_no)
            .values(paid_at=utc_now() - timedelta(days=8))
        )
        await session.commit()

    expired = await client.post(
        f"/api/v1/orders/{order_no}/after-sales",
        json={
            "sku_code": state["sku_code"],
            "type": "REFUND_ONLY",
            "reason": "expired",
            "idempotency_key": f"expired-as-{uuid4().hex}",
        },
    )
    assert expired.status_code == 409
    assert expired.json()["code"] == "AFTER_SALES_EXPIRED"

    second_order = await _create_paid_order(flow, 1)
    applied = await client.post(
        f"/api/v1/orders/{second_order}/after-sales",
        json={
            "sku_code": state["sku_code"],
            "type": "REFUND_ONLY",
            "reason": "ok",
            "idempotency_key": f"ok-as-{uuid4().hex}",
        },
    )
    after_sales_no = applied.json()["after_sales_no"]
    state["current"]["user"] = state["admin"]
    approved = await client.post(
        f"/api/v1/admin/after-sales/{after_sales_no}/approve",
        json={},
    )
    assert approved.status_code == 200
    duplicate = await client.post(
        f"/api/v1/admin/after-sales/{after_sales_no}/approve",
        json={},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "AFTER_SALES_STATUS_CONFLICT"


@pytest.mark.asyncio
async def test_unauthenticated_request(flow):
    client, _ = flow
    from app.api.dependencies import get_current_user

    app.dependency_overrides.pop(get_current_user, None)
    response = await client.get("/api/v1/orders")
    assert response.status_code == 401


def _configure_alipay(monkeypatch) -> None:
    monkeypatch.setattr(settings, "alipay_app_id", "sandbox-app")
    monkeypatch.setattr(
        settings,
        "alipay_private_key",
        SecretStr("dummy-private-key"),
    )
    monkeypatch.setattr(
        settings,
        "alipay_public_key",
        SecretStr("dummy-public-key"),
    )


async def _alipay_order(flow) -> tuple[str, str]:
    order_no = await _create_paid_order(flow, 1)
    async with AsyncSessionLocal() as session:
        order = (
            await session.execute(select(Order).where(Order.order_no == order_no))
        ).scalar_one()
        payment = (
            await session.execute(select(Payment).where(Payment.order_id == order.id))
        ).scalar_one()
        payment.channel = "ALIPAY"
        payment_no = payment.payment_no
        await session.commit()
    return order_no, payment_no


@pytest.mark.asyncio
async def test_alipay_full_refund_success(flow, monkeypatch):
    client, state = flow
    _configure_alipay(monkeypatch)
    order_no, payment_no = await _alipay_order(
        flow,
    )
    calls: list[str] = []

    async def fake_refund(
        self,
        *,
        out_trade_no,
        refund_amount,
        out_request_no,
        refund_reason=None,
    ):
        calls.append(out_request_no)
        return {
            "alipay_trade_refund_response": {
                "code": "10000",
                "fund_change": "Y",
                "out_trade_no": out_trade_no,
                "out_request_no": out_request_no,
                "refund_fee": str(refund_amount),
                "trade_no": "ALI-TRADE-1",
            }
        }

    monkeypatch.setattr(AlipayClient, "refund_trade", fake_refund)
    state["current"]["user"] = state["admin"]
    response = await client.post(
        "/api/v1/admin/refunds",
        json={
            "payment_no": payment_no,
            "amount": "19.90",
            "reason": "full refund",
            "idempotency_key": f"ali-refund-{uuid4().hex}",
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "SUCCESS"
    assert len(calls) == 1

    async with AsyncSessionLocal() as session:
        order = (
            await session.execute(select(Order).where(Order.order_no == order_no))
        ).scalar_one()
        refund = (
            await session.execute(
                select(Refund).where(Refund.refund_no == response.json()["refund_no"])
            )
        ).scalar_one()
        assert order.payment_status == "REFUNDED"
        assert refund.provider_refund_no == "ALI-TRADE-1"


@pytest.mark.asyncio
async def test_alipay_refund_failure(flow, monkeypatch):
    client, state = flow
    _configure_alipay(monkeypatch)
    _, payment_no = await _alipay_order(flow)

    async def fake_refund(
        self,
        *,
        out_trade_no,
        refund_amount,
        out_request_no,
        refund_reason=None,
    ):
        return {
            "alipay_trade_refund_response": {
                "code": "40004",
                "msg": "Business Failed",
                "sub_code": "ACQ.SYSTEM_ERROR",
                "sub_msg": "refund failed",
            }
        }

    monkeypatch.setattr(AlipayClient, "refund_trade", fake_refund)
    state["current"]["user"] = state["admin"]
    response = await client.post(
        "/api/v1/admin/refunds",
        json={
            "payment_no": payment_no,
            "amount": "19.90",
            "reason": "failure",
            "idempotency_key": f"ali-fail-{uuid4().hex}",
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "FAILED"
    assert response.json()["failure_code"] == "40004"


@pytest.mark.asyncio
async def test_alipay_refund_timeout_then_query(flow, monkeypatch):
    client, state = flow
    _configure_alipay(monkeypatch)
    _, payment_no = await _alipay_order(flow)

    async def fake_refund(
        self,
        *,
        out_trade_no,
        refund_amount,
        out_request_no,
        refund_reason=None,
    ):
        raise httpx.ReadTimeout("timeout")

    async def fake_query(self, *, out_trade_no, out_request_no):
        return {
            "alipay_trade_fastpay_refund_query_response": {
                "code": "10000",
                "refund_status": "REFUND_SUCCESS",
                "fund_change": "Y",
                "out_trade_no": out_trade_no,
                "out_request_no": out_request_no,
                "refund_amount": "19.90",
                "trade_no": "ALI-QUERY-1",
            }
        }

    monkeypatch.setattr(AlipayClient, "refund_trade", fake_refund)
    monkeypatch.setattr(AlipayClient, "query_refund", fake_query)
    state["current"]["user"] = state["admin"]
    refund = await client.post(
        "/api/v1/admin/refunds",
        json={
            "payment_no": payment_no,
            "amount": "19.90",
            "reason": "timeout",
            "idempotency_key": f"ali-timeout-{uuid4().hex}",
        },
    )
    assert refund.status_code == 201, refund.text
    assert refund.json()["status"] == "PROCESSING"
    refund_no = refund.json()["refund_no"]

    synced = await client.post(f"/api/v1/admin/refunds/{refund_no}/sync")
    assert synced.status_code == 200, synced.text
    assert synced.json()["status"] == "SUCCESS"


@pytest.mark.asyncio
async def test_alipay_refund_duplicate_idempotency_and_unknown_response(
    flow, monkeypatch
):
    client, state = flow
    _configure_alipay(monkeypatch)
    _, payment_no = await _alipay_order(flow)
    calls: list[str] = []

    async def fake_refund(
        self,
        *,
        out_trade_no,
        refund_amount,
        out_request_no,
        refund_reason=None,
    ):
        calls.append(out_request_no)
        return {
            "alipay_trade_refund_response": {
                "code": "10000",
                "fund_change": "N",
                "out_trade_no": out_trade_no,
                "out_request_no": out_request_no,
                "refund_fee": str(refund_amount),
            }
        }

    async def fake_query(self, *, out_trade_no, out_request_no):
        return {
            "alipay_trade_fastpay_refund_query_response": {
                "code": "10000",
                "refund_status": "REFUND_SUCCESS",
                "fund_change": "Y",
                "out_trade_no": out_trade_no,
                "out_request_no": out_request_no,
                "refund_amount": "19.90",
            }
        }

    monkeypatch.setattr(AlipayClient, "refund_trade", fake_refund)
    monkeypatch.setattr(AlipayClient, "query_refund", fake_query)
    state["current"]["user"] = state["admin"]
    key = f"ali-dup-{uuid4().hex}"
    payload = {
        "payment_no": payment_no,
        "amount": "19.90",
        "reason": "unknown",
        "idempotency_key": key,
    }
    first = await client.post("/api/v1/admin/refunds", json=payload)
    assert first.status_code == 201, first.text
    assert first.json()["status"] == "PROCESSING"

    second = await client.post("/api/v1/admin/refunds", json=payload)
    assert second.status_code == 201, second.text
    assert second.json()["refund_no"] == first.json()["refund_no"]
    assert len(calls) == 1

    refund_no = first.json()["refund_no"]
    synced = await client.post(f"/api/v1/admin/refunds/{refund_no}/sync")
    assert synced.status_code == 200, synced.text
    assert synced.json()["status"] == "SUCCESS"


@pytest.mark.asyncio
async def test_alipay_refund_only_after_sales_success(flow, monkeypatch):
    client, state = flow
    _configure_alipay(monkeypatch)
    order_no, _ = await _alipay_order(flow)

    async def fake_refund(
        self,
        *,
        out_trade_no,
        refund_amount,
        out_request_no,
        refund_reason=None,
    ):
        return {
            "alipay_trade_refund_response": {
                "code": "10000",
                "fund_change": "Y",
                "out_trade_no": out_trade_no,
                "out_request_no": out_request_no,
                "refund_fee": str(refund_amount),
                "trade_no": "ALI-AS-1",
            }
        }

    monkeypatch.setattr(AlipayClient, "refund_trade", fake_refund)
    applied = await client.post(
        f"/api/v1/orders/{order_no}/after-sales",
        json={
            "sku_code": state["sku_code"],
            "type": "REFUND_ONLY",
            "reason": "alipay refund",
            "idempotency_key": f"ali-as-{uuid4().hex}",
        },
    )
    assert applied.status_code == 201, applied.text
    after_sales_no = applied.json()["after_sales_no"]

    state["current"]["user"] = state["admin"]
    approved = await client.post(
        f"/api/v1/admin/after-sales/{after_sales_no}/approve",
        json={"review_note": "ok"},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "COMPLETED"

    async with AsyncSessionLocal() as session:
        order = (
            await session.execute(select(Order).where(Order.order_no == order_no))
        ).scalar_one()
        assert order.payment_status == "REFUNDED"


@pytest.mark.asyncio
async def test_alipay_partial_refund_is_rejected(flow, monkeypatch):
    client, state = flow
    _configure_alipay(monkeypatch)
    _, payment_no = await _alipay_order(flow)
    state["current"]["user"] = state["admin"]
    response = await client.post(
        "/api/v1/admin/refunds",
        json={
            "payment_no": payment_no,
            "amount": "10.00",
            "reason": "partial",
            "idempotency_key": f"ali-partial-{uuid4().hex}",
        },
    )
    assert response.status_code == 409
    assert response.json()["code"] == "REFUND_NOT_ALLOWED"


@pytest.mark.asyncio
async def test_alipay_refund_retry_reuses_out_request_no(flow, monkeypatch):
    client, state = flow
    _configure_alipay(monkeypatch)
    _, payment_no = await _alipay_order(flow)
    calls: list[str] = []
    should_fail = True

    async def fake_refund(
        self,
        *,
        out_trade_no,
        refund_amount,
        out_request_no,
        refund_reason=None,
    ):
        calls.append(out_request_no)
        if should_fail:
            return {
                "alipay_trade_refund_response": {
                    "code": "40004",
                    "msg": "temporary",
                }
            }
        return {
            "alipay_trade_refund_response": {
                "code": "10000",
                "fund_change": "Y",
                "out_trade_no": out_trade_no,
                "out_request_no": out_request_no,
                "refund_fee": str(refund_amount),
            }
        }

    monkeypatch.setattr(AlipayClient, "refund_trade", fake_refund)
    state["current"]["user"] = state["admin"]
    first = await client.post(
        "/api/v1/admin/refunds",
        json={
            "payment_no": payment_no,
            "amount": "19.90",
            "reason": "retry",
            "idempotency_key": f"ali-retry-{uuid4().hex}",
        },
    )
    assert first.status_code == 201, first.text
    assert first.json()["status"] == "FAILED"
    refund_no = first.json()["refund_no"]

    should_fail = False
    retried = await client.post(f"/api/v1/admin/refunds/{refund_no}/retry")
    assert retried.status_code == 200, retried.text
    assert retried.json()["status"] == "SUCCESS"
    assert calls == [refund_no, refund_no]
