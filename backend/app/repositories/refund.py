from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.refund import Refund


class RefundRepository:
    """Database operations for refunds."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, refund: Refund) -> Refund:
        self.session.add(refund)
        await self.session.flush()
        await self.session.refresh(refund)
        return refund

    async def save(self, refund: Refund) -> Refund:
        await self.session.flush()
        await self.session.refresh(refund)
        return refund

    async def get_by_no(
        self,
        refund_no: str,
        *,
        for_update: bool = False,
    ) -> Refund | None:
        statement = select(Refund).where(Refund.refund_no == refund_no)
        if for_update:
            statement = statement.with_for_update()
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_by_payment_and_key(
        self,
        payment_id: int,
        idempotency_key: str,
        *,
        for_update: bool = False,
    ) -> Refund | None:
        statement = select(Refund).where(
            Refund.payment_id == payment_id,
            Refund.idempotency_key == idempotency_key,
        )
        if for_update:
            statement = statement.with_for_update()
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_by_after_sale(self, after_sales_id: int) -> Refund | None:
        statement = select(Refund).where(Refund.after_sales_id == after_sales_id)
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def occupied_amount(self, payment_id: int) -> Decimal:
        statement = select(func.coalesce(func.sum(Refund.amount), 0)).where(
            Refund.payment_id == payment_id,
            Refund.status.in_(("PENDING", "PROCESSING", "SUCCESS")),
        )
        result = await self.session.execute(statement)
        return Decimal(str(result.scalar_one()))

    async def list_for_payment(self, payment_id: int) -> list[Refund]:
        statement = (
            select(Refund)
            .where(Refund.payment_id == payment_id)
            .order_by(Refund.id.asc())
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def list_admin(
        self,
        *,
        page: int,
        page_size: int,
        status: str | None = None,
    ) -> list[Refund]:
        statement = select(Refund)
        if status:
            statement = statement.where(Refund.status == status)
        statement = (
            statement.order_by(Refund.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def count_admin(self, *, status: str | None = None) -> int:
        statement = select(func.count(Refund.id))
        if status:
            statement = statement.where(Refund.status == status)
        result = await self.session.execute(statement)
        return int(result.scalar_one())
