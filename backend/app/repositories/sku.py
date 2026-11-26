"""SKU Repository.

文件职责:
- 按主键/编码/属性 hash 读取 SKU.
- 查询商品下 SKU 及库存.
- 创建和保存 SKU.

核心边界:
只执行 SQL, 不判断商品是否可售.
"""

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory import Inventory
from app.models.sku import Sku


class SkuRepository:
    """SKU 表的数据库访问对象."""

    def __init__(self, session: AsyncSession) -> None:
        """初始化实例依赖."""
        self.session = session

    async def get_by_id(
        self,
        sku_id: int,
        *,
        for_update: bool = False,
    ) -> Sku | None:
        """按主键读取 SKU, 可选行锁."""
        statement = select(Sku).where(Sku.id == sku_id)

        if for_update:
            statement = statement.with_for_update()

        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_by_code(self, sku_code: str) -> Sku | None:
        """按 SKU 编码读取."""
        statement = select(Sku).where(Sku.sku_code == sku_code)
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_by_product_hash(
        self,
        *,
        product_id: int,
        attributes_hash: str,
    ) -> Sku | None:
        """按商品和属性 hash 读取 SKU, 防止重复规格."""
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
        """按商品读取 SKU, 可按状态过滤."""
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
        """左连接库存读取 SKU, 库存缺失时返回 None."""
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
        """创建 SKU, 只 flush 不 commit."""
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
        """刷新 SKU, 不主动 commit."""
        await self.session.flush()
        await self.session.refresh(sku)
        return sku
