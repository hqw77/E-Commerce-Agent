from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory import Inventory
from app.models.sku import Sku


class SkuRepository:
    """Database operations for SKUs."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(
        self,
        sku_id: int,
        *,
        for_update: bool = False,
    ) -> Sku | None:
        statement = select(Sku).where(Sku.id == sku_id)

        if for_update:
            statement = statement.with_for_update()

        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_by_code(self, sku_code: str) -> Sku | None:
        statement = select(Sku).where(Sku.sku_code == sku_code)
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_by_product_hash(
        self,
        *,
        product_id: int,
        attributes_hash: str,
    ) -> Sku | None:
        statement = select(Sku).where(
            Sku.product_id == product_id,
            Sku.attributes_hash == attributes_hash,
        )
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def list_by_product(
        self,
        product_id: int,
        *,
        status: str | None = None,
    ) -> list[Sku]:
        statement = select(Sku).where(Sku.product_id == product_id).order_by(Sku.id)

        if status is not None:
            statement = statement.where(Sku.status == status)

        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def list_with_inventory(
        self,
        product_id: int,
        *,
        status: str | None = None,
    ) -> list[tuple[Sku, Inventory | None]]:
        statement = (
            select(Sku, Inventory)
            .outerjoin(Inventory, Inventory.sku_id == Sku.id)
            .where(Sku.product_id == product_id)
            .order_by(Sku.id)
        )

        if status is not None:
            statement = statement.where(Sku.status == status)

        result = await self.session.execute(statement)
        return list(result.all())

    async def create(
        self,
        *,
        product_id: int,
        sku_code: str,
        attributes: dict[str, str],
        attributes_hash: str,
        price: Decimal,
        status: str,
    ) -> Sku:
        sku = Sku(
            product_id=product_id,
            sku_code=sku_code,
            attributes=attributes,
            attributes_hash=attributes_hash,
            price=price,
            status=status,
        )
        self.session.add(sku)
        await self.session.flush()
        await self.session.refresh(sku)
        return sku

    async def save(self, sku: Sku) -> Sku:
        await self.session.flush()
        await self.session.refresh(sku)
        return sku
