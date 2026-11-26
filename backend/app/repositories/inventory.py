"""库存 Repository.

文件职责:
- 以原子 UPDATE 修改 total_quantity 和 reserved_quantity.
- 提供行锁读取和批量读取.

核心边界:
Repository 只返回受影响行数, 由 Service 根据 0/1 判断并发冲突.
"""

from collections.abc import Sequence

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory import Inventory


class InventoryRepository:
    """库存表的数据库访问对象."""

    def __init__(self, session: AsyncSession) -> None:
        """初始化实例依赖."""
        self.session = session

    async def get_by_sku_id(self, sku_id: int) -> Inventory | None:
        """按 SKU 读取库存, 不加锁."""
        statement = select(Inventory).where(Inventory.sku_id == sku_id)
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_by_sku_id_for_update(
        self,
        sku_id: int,
    ) -> Inventory | None:
        """按 SKU 读取并加行锁, 用于需要读后改的库存操作."""
        statement = (
            select(Inventory).where(Inventory.sku_id == sku_id).with_for_update()
        )
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_by_sku_ids(
        self,
        sku_ids: Sequence[int],
    ) -> dict[int, Inventory]:
        """批量读取库存, 返回 sku_id 到 Inventory 的映射."""
        if not sku_ids:
            return {}

        statement = select(Inventory).where(Inventory.sku_id.in_(sku_ids))
        result = await self.session.execute(statement)
        return {inventory.sku_id: inventory for inventory in result.scalars().all()}

    async def create(self, *, sku_id: int) -> Inventory:
        """为新 SKU 创建零库存记录."""
        inventory = Inventory(
            sku_id=sku_id,
            total_quantity=0,
            reserved_quantity=0,
        )
        self.session.add(inventory)
        await self.session.flush()
        await self.session.refresh(inventory)
        return inventory

    async def update_total(
        self,
        sku_id: int,
        *,
        delta: int = 0,
        absolute: int | None = None,
        require_available: int | None = None,
    ) -> int:
        """原子更新总库存; 返回 0 表示条件不满足或库存不存在."""
        statement = update(Inventory).where(Inventory.sku_id == sku_id)

        if absolute is not None:
            statement = statement.values(total_quantity=absolute).where(
                Inventory.total_quantity == 0,
                Inventory.reserved_quantity == 0,
            )
        else:
            statement = statement.values(
                total_quantity=Inventory.total_quantity + delta
            )

        if delta < 0:
            statement = statement.where(
                Inventory.total_quantity + delta >= Inventory.reserved_quantity
            )

        if require_available is not None:
            statement = statement.where(
                Inventory.total_quantity - Inventory.reserved_quantity
                >= require_available
            )

        result = await self.session.execute(statement)
        return int(getattr(result, "rowcount", 0) or 0)

    async def reserve(self, sku_id: int, quantity: int) -> int:
        """原子预占库存; WHERE 条件保证可用量足够."""
        statement = (
            update(Inventory)
            .where(
                Inventory.sku_id == sku_id,
                Inventory.total_quantity - Inventory.reserved_quantity >= quantity,
            )
            .values(reserved_quantity=Inventory.reserved_quantity + quantity)
        )
        result = await self.session.execute(statement)
        return int(getattr(result, "rowcount", 0) or 0)

    async def release(self, sku_id: int, quantity: int) -> int:
        """原子释放预占; 防止 reserved 变成负数."""
        statement = (
            update(Inventory)
            .where(
                Inventory.sku_id == sku_id,
                Inventory.reserved_quantity >= quantity,
            )
            .values(reserved_quantity=Inventory.reserved_quantity - quantity)
        )
        result = await self.session.execute(statement)
        return int(getattr(result, "rowcount", 0) or 0)

    async def deduct_reserved(self, sku_id: int, quantity: int) -> int:
        """发货时同时扣减总量和预占量."""
        statement = (
            update(Inventory)
            .where(
                Inventory.sku_id == sku_id,
                Inventory.reserved_quantity >= quantity,
                Inventory.total_quantity >= quantity,
            )
            .values(
                total_quantity=Inventory.total_quantity - quantity,
                reserved_quantity=Inventory.reserved_quantity - quantity,
            )
        )
        result = await self.session.execute(statement)
        return int(getattr(result, "rowcount", 0) or 0)

    async def restock(self, sku_id: int, quantity: int) -> int:
        """退货入库时增加总库存."""
        statement = (
            update(Inventory)
            .where(Inventory.sku_id == sku_id)
            .values(total_quantity=Inventory.total_quantity + quantity)
        )
        result = await self.session.execute(statement)
        return int(getattr(result, "rowcount", 0) or 0)

    async def direct_outbound(self, sku_id: int, quantity: int) -> int:
        """不经过预占, 直接从可用库存出库."""
        statement = (
            update(Inventory)
            .where(
                Inventory.sku_id == sku_id,
                Inventory.total_quantity - Inventory.reserved_quantity >= quantity,
            )
            .values(total_quantity=Inventory.total_quantity - quantity)
        )
        result = await self.session.execute(statement)
        return int(getattr(result, "rowcount", 0) or 0)
