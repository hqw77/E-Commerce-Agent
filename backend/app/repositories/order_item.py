from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order_item import OrderItem


class OrderItemRepository:
    """Database operations for order line snapshots."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        order_id: int,
        product_id: int,
        sku_id: int,
        product_no: str,
        product_name: str,
        sku_code: str,
        sku_attributes: dict[str, Any],
        currency: str,
        unit_price: Decimal,
        quantity: int,
        line_amount: Decimal,
    ) -> OrderItem:
        item = OrderItem(
            order_id=order_id,
            product_id=product_id,
            sku_id=sku_id,
            product_no=product_no,
            product_name=product_name,
            sku_code=sku_code,
            sku_attributes=sku_attributes,
            currency=currency,
            unit_price=unit_price,
            quantity=quantity,
            line_amount=line_amount,
        )
        self.session.add(item)
        await self.session.flush()
        await self.session.refresh(item)
        return item

    async def list_by_order(self, order_id: int) -> list[OrderItem]:
        statement = (
            select(OrderItem)
            .where(OrderItem.order_id == order_id)
            .order_by(OrderItem.sku_id.asc())
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def get_by_order_and_sku(
        self,
        order_id: int,
        sku_code: str,
        *,
        for_update: bool = False,
    ) -> OrderItem | None:
        statement = select(OrderItem).where(
            OrderItem.order_id == order_id,
            OrderItem.sku_code == sku_code,
        )
        if for_update:
            statement = statement.with_for_update()
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_by_id(
        self,
        item_id: int,
        *,
        for_update: bool = False,
    ) -> OrderItem | None:
        statement = select(OrderItem).where(OrderItem.id == item_id)
        if for_update:
            statement = statement.with_for_update()
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()
