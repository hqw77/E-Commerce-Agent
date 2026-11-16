from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.order import Order


class OrderRepository:
    """Database operations for orders."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, order: Order) -> Order:
        self.session.add(order)
        await self.session.flush()
        await self.session.refresh(order)
        return order

    async def save(self, order: Order) -> Order:
        await self.session.flush()
        await self.session.refresh(order)
        return order

    async def get_by_no(
        self,
        order_no: str,
        *,
        for_update: bool = False,
        with_items: bool = False,
    ) -> Order | None:
        statement = select(Order).where(Order.order_no == order_no)
        if with_items:
            statement = statement.options(selectinload(Order.items))
        if for_update:
            statement = statement.with_for_update()
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_by_id(
        self,
        order_id: int,
        *,
        for_update: bool = False,
    ) -> Order | None:
        statement = select(Order).where(Order.id == order_id)
        if for_update:
            statement = statement.with_for_update()
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_by_user_and_key(
        self,
        user_id: int,
        idempotency_key: str,
        *,
        for_update: bool = False,
    ) -> Order | None:
        statement = select(Order).where(
            Order.user_id == user_id,
            Order.idempotency_key == idempotency_key,
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
        status: str | None = None,
    ) -> list[Order]:
        statement = select(Order).where(Order.user_id == user_id)
        if status:
            statement = statement.where(Order.status == status)
        statement = (
            statement.options(selectinload(Order.items))
            .order_by(Order.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def count_for_user(
        self,
        user_id: int,
        *,
        status: str | None = None,
    ) -> int:
        statement = select(func.count(Order.id)).where(Order.user_id == user_id)
        if status:
            statement = statement.where(Order.status == status)
        result = await self.session.execute(statement)
        return int(result.scalar_one())

    async def list_admin(
        self,
        *,
        page: int,
        page_size: int,
        status: str | None = None,
    ) -> list[Order]:
        statement = select(Order)
        if status:
            statement = statement.where(Order.status == status)
        statement = (
            statement.options(selectinload(Order.items))
            .order_by(Order.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def count_admin(self, *, status: str | None = None) -> int:
        statement = select(func.count(Order.id))
        if status:
            statement = statement.where(Order.status == status)
        result = await self.session.execute(statement)
        return int(result.scalar_one())

    async def list_expired_pending(self) -> list[Order]:
        from app.utils.order import utc_now

        statement = (
            select(Order)
            .where(
                Order.status == "PENDING_PAYMENT",
                Order.expires_at <= utc_now(),
            )
            .order_by(Order.id.asc())
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def sum_paid_amount(self, order_id: int) -> Decimal:
        statement = select(func.coalesce(func.sum(Order.paid_amount), 0)).where(
            Order.id == order_id
        )
        result = await self.session.execute(statement)
        return Decimal(str(result.scalar_one()))
