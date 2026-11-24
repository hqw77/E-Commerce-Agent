"""Core order and after-sales lifecycle after payment removal."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio
from app.core.exceptions import ConflictException
from app.db.session import AsyncSessionLocal
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
from app.schemas.after_sale import (
    AfterSaleApplyRequest,
    CompleteExchangeRequest,
    ReturnShipmentRequest,
)
from app.schemas.order import OrderCreateRequest, ShipOrderRequest
from app.services.after_sale import AfterSaleService
from app.services.order import OrderService
from app.utils.order import utc_now
from pydantic import ValidationError
from sqlalchemy import delete, select

PREFIX = "t23life"


def _hash(attributes: dict[str, str]) -> str:
    return hashlib.sha256(
        json.dumps(attributes, sort_keys=True).encode("utf-8")
    ).hexdigest()


@pytest_asyncio.fixture
async def seed():
    async with AsyncSessionLocal() as session:
        user = User(
            email=f"{PREFIX}-{uuid4().hex}@example.com",
            password_hash="x",
            is_active=True,
            is_admin=False,
        )
        admin = User(
            email=f"{PREFIX}-admin-{uuid4().hex}@example.com",
            password_hash="x",
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
            name="Lifecycle product",
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
            price=Decimal("19.90"),
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

        values = {
            "user_id": user.id,
            "admin_id": admin.id,
            "category_id": category.id,
            "product_id": product.id,
            "sku_id": sku.id,
            "sku_code": sku.sku_code,
        }
    try:
        yield values
    finally:
        async with AsyncSessionLocal() as session:
            order_ids = select(Order.id).where(Order.user_id == values["user_id"])
            await session.execute(
                delete(AfterSale).where(AfterSale.user_id == values["user_id"])
            )
            await session.execute(
                delete(OrderItem).where(OrderItem.order_id.in_(order_ids))
            )
            # Refund/Payment legacy rows are not created by the new tests.
            await session.execute(
                delete(Order).where(Order.user_id == values["user_id"])
            )
            await session.execute(
                delete(InventoryTransaction).where(
                    InventoryTransaction.sku_id == values["sku_id"]
                )
            )
            await session.execute(
                delete(Inventory).where(Inventory.sku_id == values["sku_id"])
            )
            await session.execute(delete(Sku).where(Sku.id == values["sku_id"]))
            await session.execute(
                delete(Product).where(Product.id == values["product_id"])
            )
            await session.execute(
                delete(Category).where(Category.id == values["category_id"])
            )
            await session.execute(
                delete(User).where(
                    User.id.in_([values["user_id"], values["admin_id"]])
                )
            )
            await session.commit()


def _order_request(seed: dict, *, quantity: int = 2) -> OrderCreateRequest:
    return OrderCreateRequest(
        items=[{"sku_code": seed["sku_code"], "quantity": quantity}],
        receiver_name="Lifecycle User",
        receiver_phone="13800000000",
        receiver_address="Shanghai",
        idempotency_key=f"{PREFIX}-{uuid4().hex}",
    )


async def _create(seed: dict, quantity: int = 2) -> Order:
    async with AsyncSessionLocal() as session:
        return await OrderService(session).create_order(
            user_id=seed["user_id"],
            request=_order_request(seed, quantity=quantity),
        )


@pytest.mark.asyncio
async def test_create_order_reserves_and_cancel_releases(seed):
    order = await _create(seed, 2)
    assert order.status == "CREATED"
    assert order.fulfillment_status == "UNSHIPPED"
    async with AsyncSessionLocal() as session:
        inventory = (
            await session.execute(
                select(Inventory).where(Inventory.sku_id == seed["sku_id"])
            )
        ).scalar_one()
        assert inventory.reserved_quantity == 2
        cancelled = await OrderService(session).cancel_order(
            user_id=seed["user_id"],
            order_no=order.order_no,
            reason="test",
        )
        assert cancelled.status == "CANCELLED"
        await session.refresh(inventory)
        assert inventory.reserved_quantity == 0


@pytest.mark.asyncio
async def test_ship_deducts_and_complete_lifecycle(seed):
    order = await _create(seed, 2)
    async with AsyncSessionLocal() as session:
        service = OrderService(session)
        shipped = await service.ship(
            order_no=order.order_no,
            request=ShipOrderRequest(shipping_carrier="SF", tracking_no="SF123"),
        )
        assert shipped.fulfillment_status == "SHIPPED"
        delivered = await service.deliver(order_no=order.order_no)
        assert delivered.fulfillment_status == "DELIVERED"
        completed = await service.complete(order_no=order.order_no)
        assert completed.status == "COMPLETED"
        assert completed.fulfillment_status == "COMPLETED"
        inventory = (
            await session.execute(
                select(Inventory).where(Inventory.sku_id == seed["sku_id"])
            )
        ).scalar_one()
        assert inventory.total_quantity == 8
        assert inventory.reserved_quantity == 0


@pytest.mark.asyncio
async def test_only_exchange_after_sale_and_inventory_flow(seed):
    order = await _create(seed, 2)
    async with AsyncSessionLocal() as session:
        service = OrderService(session)
        await service.ship(
            order_no=order.order_no,
            request=ShipOrderRequest(shipping_carrier="SF", tracking_no="SF123"),
        )
        await service.deliver(order_no=order.order_no)
        after_sale = await AfterSaleService(session).apply(
            user_id=seed["user_id"],
            order_no=order.order_no,
            request=AfterSaleApplyRequest(
                sku_code=seed["sku_code"],
                type="EXCHANGE",
                reason="size",
                idempotency_key=f"{PREFIX}-as-{uuid4().hex}",
            ),
        )
        assert after_sale.status == "PENDING_REVIEW"
        approved = await AfterSaleService(session).approve(
            after_sales_no=after_sale.after_sales_no,
            admin_id=seed["admin_id"],
            review_note="ok",
        )
        assert approved.status == "WAITING_RETURN"
        shipped_back = await AfterSaleService(session).submit_return_shipment(
            user_id=seed["user_id"],
            after_sales_no=after_sale.after_sales_no,
            request=ReturnShipmentRequest(
                return_carrier="SF",
                return_tracking_no="RET123",
            ),
        )
        assert shipped_back.status == "RETURN_SHIPPED"
        received = await AfterSaleService(session).receive(
            after_sales_no=after_sale.after_sales_no,
            admin_id=seed["admin_id"],
        )
        assert received.status == "RECEIVED"
        completed = await AfterSaleService(session).complete_exchange(
            after_sales_no=after_sale.after_sales_no,
            request=CompleteExchangeRequest(
                replacement_carrier="SF",
                replacement_tracking_no="OUT123",
            ),
        )
        assert completed.status == "COMPLETED"
        inventory = (
            await session.execute(
                select(Inventory).where(Inventory.sku_id == seed["sku_id"])
            )
        ).scalar_one()
        # 10 - 2 shipped + 2 returned - 2 replacement = 8.
        assert inventory.total_quantity == 8
        assert inventory.reserved_quantity == 0


def test_refund_after_sale_request_is_rejected():
    with pytest.raises(ValidationError):
        AfterSaleApplyRequest(
            sku_code="SKU",
            type="REFUND_ONLY",
            reason="no",
            idempotency_key="key-1",
        )


def test_payment_and_refund_routes_are_removed():
    paths = app.openapi()["paths"]
    assert "/api/v1/payments" not in paths
    assert "/api/v1/admin/payments" not in paths
    assert "/api/v1/admin/refunds" not in paths


@pytest.mark.asyncio
async def test_cancelled_order_cannot_be_shipped(seed):
    order = await _create(seed, 1)
    async with AsyncSessionLocal() as session:
        await OrderService(session).cancel_order(
            user_id=seed["user_id"],
            order_no=order.order_no,
        )
        with pytest.raises(ConflictException):
            await OrderService(session).ship(
                order_no=order.order_no,
                request=ShipOrderRequest(
                    shipping_carrier="SF",
                    tracking_no="SF404",
                ),
            )
