from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category
from app.models.product import Product


class CategoryRepository:
    """Database operations for the category tree."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(
        self,
        category_id: int,
        *,
        for_update: bool = False,
    ) -> Category | None:
        statement = select(Category).where(Category.id == category_id)

        if for_update:
            statement = statement.with_for_update()

        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_by_ids_for_update(
        self,
        category_ids: Sequence[int],
    ) -> list[Category]:
        if not category_ids:
            return []

        statement = (
            select(Category)
            .where(Category.id.in_(category_ids))
            .order_by(Category.id)
            .with_for_update()
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def list_all(self) -> list[Category]:
        statement = select(Category).order_by(
            Category.parent_id,
            Category.sort_order,
            Category.id,
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def has_children(
        self,
        category_id: int,
        *,
        enabled_only: bool = False,
    ) -> bool:
        statement = select(Category.id).where(Category.parent_id == category_id)

        if enabled_only:
            statement = statement.where(Category.status == "ENABLED")

        result = await self.session.execute(statement.limit(1))
        return result.scalar_one_or_none() is not None

    async def has_products(
        self,
        category_id: int,
        *,
        status: str | None = None,
    ) -> bool:
        statement = select(Product.id).where(Product.category_id == category_id)

        if status is not None:
            statement = statement.where(Product.status == status)

        result = await self.session.execute(statement.limit(1))
        return result.scalar_one_or_none() is not None

    async def create(
        self,
        *,
        parent_id: int | None,
        name: str,
        sort_order: int,
    ) -> Category:
        category = Category(
            parent_id=parent_id,
            name=name,
            sort_order=sort_order,
        )
        self.session.add(category)
        await self.session.flush()
        await self.session.refresh(category)
        return category

    async def update(
        self,
        category: Category,
        *,
        name: str | None = None,
        sort_order: int | None = None,
        status: str | None = None,
    ) -> Category:
        if name is not None:
            category.name = name
        if sort_order is not None:
            category.sort_order = sort_order
        if status is not None:
            category.status = status

        await self.session.flush()
        await self.session.refresh(category)
        return category
