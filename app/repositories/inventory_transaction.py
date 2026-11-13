from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory_transaction import InventoryTransaction


class InventoryTransactionRepository:
    """Database operations for the inventory ledger."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_key(
        self,
        idempotency_key: str,
        *,
        for_update: bool = False,
    ) -> InventoryTransaction | None:
        statement = select(InventoryTransaction).where(
            InventoryTransaction.idempotency_key == idempotency_key
        )

        if for_update:
            statement = statement.with_for_update()

        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def exists_for_sku(self, sku_id: int) -> bool:
        statement = (
            select(InventoryTransaction.id)
            .where(InventoryTransaction.sku_id == sku_id)
            .limit(1)
        )
        result = await self.session.execute(statement)
        return result.scalar_one_or_none() is not None

    async def create(
        self,
        *,
        sku_id: int,
        transaction_type: str,
        total_delta: int,
        reserved_delta: int,
        total_after: int,
        reserved_after: int,
        idempotency_key: str,
        business_type: str,
        operator_id: int | None,
        remark: str | None,
    ) -> InventoryTransaction:
        transaction = InventoryTransaction(
            sku_id=sku_id,
            transaction_type=transaction_type,
            total_delta=total_delta,
            reserved_delta=reserved_delta,
            total_after=total_after,
            reserved_after=reserved_after,
            idempotency_key=idempotency_key,
            business_type=business_type,
            operator_id=operator_id,
            remark=remark,
        )
        self.session.add(transaction)
        await self.session.flush()
        await self.session.refresh(transaction)
        return transaction

    async def list_by_sku(
        self,
        sku_id: int,
        *,
        page: int,
        page_size: int,
    ) -> list[InventoryTransaction]:
        statement = (
            select(InventoryTransaction)
            .where(InventoryTransaction.sku_id == sku_id)
            .order_by(InventoryTransaction.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def count_by_sku(self, sku_id: int) -> int:
        statement = select(func.count(InventoryTransaction.id)).where(
            InventoryTransaction.sku_id == sku_id
        )
        result = await self.session.execute(statement)
        return int(result.scalar_one())
