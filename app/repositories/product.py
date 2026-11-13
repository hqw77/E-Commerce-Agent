from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.models.product import Product


class ProductRepository:
    """Database operations for products."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(
        self,
        product_id: int,
        *,
        for_update: bool = False,
    ) -> Product | None:
        statement = select(Product).where(Product.id == product_id)

        if for_update:
            statement = statement.with_for_update()

        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_by_product_no(self, product_no: str) -> Product | None:
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
    ) -> Product:
        product = Product(
            product_no=product_no,
            category_id=category_id,
            name=name,
            description=description,
            status="DRAFT",
        )
        self.session.add(product)
        await self.session.flush()
        await self.session.refresh(product)
        return product

    async def save(self, product: Product) -> Product:
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
