"""商品 Repository.

文件职责:
- 按主键/商品号读取商品.
- 创建和保存商品.
- 按状态/分类/关键词分页查询.

核心边界:
只执行 SQL, 不判断商品状态迁移.
"""

from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.models.product import Product


class ProductRepository:
    """商品表的数据库访问对象."""

    def __init__(self, session: AsyncSession) -> None:
        """初始化实例依赖."""
        self.session = session

    async def get_by_id(
        self,
        product_id: int,
        *,
        for_update: bool = False,
    ) -> Product | None:
        """按主键读取商品, 可选行锁."""
        statement = select(Product).where(Product.id == product_id)

        if for_update:
            statement = statement.with_for_update()

        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_by_product_no(self, product_no: str) -> Product | None:
        """按商品号读取商品."""
        statement = select(Product).where(Product.product_no == product_no)
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        product_no: str,
        category_id: int,
        name: str,
        description: str | None,
        image_url: str | None = None,
    ) -> Product:
        """创建 DRAFT 商品, 只 flush 不 commit."""
        product = Product(
            product_no=product_no,
            category_id=category_id,
            name=name,
            description=description,
            image_url=image_url,
            status="DRAFT",
        )
        self.session.add(product)
        await self.session.flush()
        await self.session.refresh(product)
        return product

    async def save(self, product: Product) -> Product:
        """刷新已修改商品, 不主动 commit."""
        await self.session.flush()
        await self.session.refresh(product)
        return product

    @staticmethod
    def _filters(
        *,
        status: str | None,
        category_id: int | None,
        keyword: str | None,
    ) -> list[ColumnElement[bool]]:
        """构造状态/分类/关键词过滤条件."""
        filters: list[ColumnElement[bool]] = []

        if status is not None:
            filters.append(Product.status == status)
        if category_id is not None:
            filters.append(Product.category_id == category_id)
        if keyword:
            filters.append(Product.name.like(f"%{keyword}%"))

        return filters

    async def count(
        self,
        *,
        status: str | None = None,
        category_id: int | None = None,
        keyword: str | None = None,
    ) -> int:
        """按过滤条件统计商品数."""
        statement = select(func.count(Product.id)).where(
            *self._filters(
                status=status,
                category_id=category_id,
                keyword=keyword,
            )
        )
        result = await self.session.execute(statement)
        return int(result.scalar_one())

    async def list_products(
        self,
        *,
        status: str | None,
        category_id: int | None,
        keyword: str | None,
        page: int,
        page_size: int,
    ) -> Sequence[Product]:
        """按过滤条件分页查询商品, 最新在前."""
        statement = (
            select(Product)
            .where(
                *self._filters(
                    status=status,
                    category_id=category_id,
                    keyword=keyword,
                )
            )
            .order_by(Product.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())
