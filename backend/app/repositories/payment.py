from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.payment import Payment


class PaymentRepository:
    """Database operations for payment attempts."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, payment: Payment) -> Payment:
        self.session.add(payment)
        await self.session.flush()
        await self.session.refresh(payment)
        return payment

    async def save(self, payment: Payment) -> Payment:
        await self.session.flush()
        await self.session.refresh(payment)
        return payment

    async def get_by_order(
        self,
        order_id: int,
        *,
        for_update: bool = False,
    ) -> Payment | None:
        statement = select(Payment).where(Payment.order_id == order_id)
        if for_update:
            statement = statement.with_for_update()
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_by_no(
        self,
        payment_no: str,
        *,
        for_update: bool = False,
    ) -> Payment | None:
        statement = select(Payment).where(Payment.payment_no == payment_no)
        if for_update:
            statement = statement.with_for_update()
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_by_id_for_update(self, payment_id: int) -> Payment | None:
        statement = select(Payment).where(Payment.id == payment_id).with_for_update()
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_by_id(self, payment_id: int) -> Payment | None:
        statement = select(Payment).where(Payment.id == payment_id)
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def list_for_user(
        self,
        user_id: int,
        *,
        page: int,
        page_size: int,
    ) -> list[Payment]:
        statement = (
            select(Payment)
            .where(Payment.user_id == user_id)
            .order_by(Payment.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def count_for_user(self, user_id: int) -> int:
        statement = select(func.count(Payment.id)).where(Payment.user_id == user_id)
        result = await self.session.execute(statement)
        return int(result.scalar_one())

    async def list_admin(
        self,
        *,
        page: int,
        page_size: int,
        status: str | None = None,
    ) -> list[Payment]:
        statement = select(Payment)
        if status:
            statement = statement.where(Payment.status == status)
        statement = (
            statement.order_by(Payment.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def count_admin(self, *, status: str | None = None) -> int:
        statement = select(func.count(Payment.id))
        if status:
            statement = statement.where(Payment.status == status)
        result = await self.session.execute(statement)
        return int(result.scalar_one())

    async def get_by_provider_trade(
        self,
        provider_trade_no: str,
    ) -> Payment | None:
        statement = select(Payment).where(
            Payment.provider_trade_no == provider_trade_no
        )
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def total_refunded(self, payment_id: int) -> Decimal:
        statement = select(func.coalesce(func.sum(Payment.refunded_amount), 0)).where(
            Payment.id == payment_id
        )
        result = await self.session.execute(statement)
        return Decimal(str(result.scalar_one()))
