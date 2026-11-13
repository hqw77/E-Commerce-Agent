from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.after_sale import AfterSale

ACTIVE_AFTER_SALE_STATUSES = (
    "PENDING_REVIEW",
    "APPROVED",
    "WAITING_RETURN",
    "RETURN_SHIPPED",
    "RECEIVED",
    "REFUNDING",
    "REFUND_FAILED",
)


class AfterSaleRepository:
    """Database operations for after-sales requests."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, after_sale: AfterSale) -> AfterSale:
        self.session.add(after_sale)
        await self.session.flush()
        await self.session.refresh(after_sale)
        return after_sale

    async def save(self, after_sale: AfterSale) -> AfterSale:
        await self.session.flush()
        await self.session.refresh(after_sale)
        return after_sale

    async def get_by_no(
        self,
        after_sales_no: str,
        *,
        for_update: bool = False,
    ) -> AfterSale | None:
        statement = select(AfterSale).where(AfterSale.after_sales_no == after_sales_no)
        if for_update:
            statement = statement.with_for_update()
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_by_id(self, after_sales_id: int) -> AfterSale | None:
        statement = select(AfterSale).where(AfterSale.id == after_sales_id)
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_by_user_and_key(
        self,
        user_id: int,
        idempotency_key: str,
        *,
        for_update: bool = False,
    ) -> AfterSale | None:
        statement = select(AfterSale).where(
            AfterSale.user_id == user_id,
            AfterSale.idempotency_key == idempotency_key,
        )
        if for_update:
            statement = statement.with_for_update()
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_active_for_item(
        self,
        order_item_id: int,
        *,
        for_update: bool = False,
    ) -> AfterSale | None:
        statement = select(AfterSale).where(
            AfterSale.order_item_id == order_item_id,
            AfterSale.status.in_(ACTIVE_AFTER_SALE_STATUSES),
        )
        if for_update:
            statement = statement.with_for_update()
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def list_for_user(
        self,
        user_id: int,
        *,
        page: int,
        page_size: int,
    ) -> list[AfterSale]:
        statement = (
            select(AfterSale)
            .where(AfterSale.user_id == user_id)
            .order_by(AfterSale.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def count_for_user(self, user_id: int) -> int:
        statement = select(func.count(AfterSale.id)).where(AfterSale.user_id == user_id)
        result = await self.session.execute(statement)
        return int(result.scalar_one())

    async def list_for_order(self, order_id: int) -> list[AfterSale]:
        statement = (
            select(AfterSale)
            .where(AfterSale.order_id == order_id)
            .order_by(AfterSale.id.asc())
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def list_admin(
        self,
        *,
        page: int,
        page_size: int,
        status: str | None = None,
    ) -> list[AfterSale]:
        statement = select(AfterSale)
        if status:
            statement = statement.where(AfterSale.status == status)
        statement = (
            statement.order_by(AfterSale.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def count_admin(self, *, status: str | None = None) -> int:
        statement = select(func.count(AfterSale.id))
        if status:
            statement = statement.where(AfterSale.status == status)
        result = await self.session.execute(statement)
        return int(result.scalar_one())

    @staticmethod
    def same_fingerprint(
        after_sale: AfterSale,
        *,
        order_id: int,
        order_item_id: int,
        type: str,
        quantity: int,
        requested_amount: Decimal,
        reason: str,
        description: str | None,
        evidence_urls: list[str] | None,
    ) -> bool:
        return (
            after_sale.order_id == order_id
            and after_sale.order_item_id == order_item_id
            and after_sale.type == type
            and after_sale.quantity == quantity
            and after_sale.requested_amount == requested_amount
            and after_sale.reason == reason
            and after_sale.description == description
            and after_sale.evidence_urls == evidence_urls
        )


def after_sale_fingerprint_payload(
    *,
    order_no: str,
    sku_code: str,
    type: str,
    quantity: int,
    reason: str,
    description: str | None,
    evidence_urls: list[str] | None,
) -> dict[str, Any]:
    """Expose the payload used by the service for consistent comparison."""
    return {
        "order_no": order_no,
        "sku_code": sku_code,
        "type": type,
        "quantity": quantity,
        "reason": reason,
        "description": description,
        "evidence_urls": evidence_urls,
    }
