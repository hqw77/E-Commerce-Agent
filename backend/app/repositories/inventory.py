from collections.abc import Sequence

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory import Inventory


class InventoryRepository:
    """Database operations for inventory rows."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_sku_id(self, sku_id: int) -> Inventory | None:
        statement = select(Inventory).where(Inventory.sku_id == sku_id)
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_by_sku_id_for_update(
        self,
        sku_id: int,
    ) -> Inventory | None:
        statement = (
            select(Inventory).where(Inventory.sku_id == sku_id).with_for_update()
        )
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_by_sku_ids(
        self,
        sku_ids: Sequence[int],
    ) -> dict[int, Inventory]:
        if not sku_ids:
            return {}

        statement = select(Inventory).where(Inventory.sku_id.in_(sku_ids))
        result = await self.session.execute(statement)
        return {inventory.sku_id: inventory for inventory in result.scalars().all()}

    async def create(self, *, sku_id: int) -> Inventory:
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
        statement = (
            update(Inventory)
            .where(Inventory.sku_id == sku_id)
            .values(total_quantity=Inventory.total_quantity + quantity)
        )
        result = await self.session.execute(statement)
        return int(getattr(result, "rowcount", 0) or 0)

    async def direct_outbound(self, sku_id: int, quantity: int) -> int:
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
