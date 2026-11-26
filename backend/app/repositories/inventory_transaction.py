"""库存流水 Repository.

文件职责:
- 按幂等键读写流水.
- 创建库存变更流水.
- 分页查询 SKU 流水.

核心边界:
流水只追加, 不允许原地修改.
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory_transaction import InventoryTransaction


class InventoryTransactionRepository:
    """库存流水表的数据库访问对象."""

    def __init__(self, session: AsyncSession) -> None:
        """初始化实例依赖."""
        self.session = session

    async def get_by_key(
        self,
        idempotency_key: str,
        *,
        for_update: bool = False,
    ) -> InventoryTransaction | None:
        """按幂等键读取流水, 可选行锁."""
        statement = select(InventoryTransaction).where(
            InventoryTransaction.idempotency_key == idempotency_key
        )

        if for_update:
            statement = statement.with_for_update()

        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def exists_for_sku(self, sku_id: int) -> bool:
        """判断 SKU 是否已有库存流水, 用于初始化幂等."""
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
        business_id: int | None = None,
        business_item_id: int | None = None,
    ) -> InventoryTransaction:
        """创建一条库存流水, 只 flush 不 commit."""
        transaction = InventoryTransaction(
            sku_id=sku_id,
            transaction_type=transaction_type,
            total_delta=total_delta,
            reserved_delta=reserved_delta,
            total_after=total_after,
            reserved_after=reserved_after,
            idempotency_key=idempotency_key,
            business_type=business_type,
            business_id=business_id,
            business_item_id=business_item_id,
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
        """分页查询 SKU 流水, 最新在前."""
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
        """统计 SKU 流水数量."""
        statement = select(func.count(InventoryTransaction.id)).where(
            InventoryTransaction.sku_id == sku_id
        )
        result = await self.session.execute(statement)
        return int(result.scalar_one())
