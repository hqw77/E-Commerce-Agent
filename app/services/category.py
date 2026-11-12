from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictException, ResourceNotFoundException
from app.models.category import Category
from app.repositories.category import CategoryRepository
from app.schemas.category import CategoryTreeNode


class CategoryService:
    """Business rules for the category tree."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = CategoryRepository(session)

    @asynccontextmanager
    async def _transaction(self) -> AsyncIterator[None]:
        """Reuse the request transaction when one is already open."""
        if self.session.in_transaction():
            try:
                yield
                await self.session.commit()
            except Exception:
                await self.session.rollback()
                raise
        else:
            async with self.session.begin():
                yield

    async def create_category(
        self,
        *,
        parent_id: int | None,
        name: str,
        sort_order: int,
    ) -> Category:
        async with self._transaction():
            if parent_id is not None:
                parent = await self.repository.get_by_id(
                    parent_id,
                    for_update=True,
                )

                if parent is None:
                    raise ResourceNotFoundException(
                        message="Parent category not found",
                        code="CATEGORY_PARENT_NOT_FOUND",
                    )

                if parent.status != "ENABLED":
                    raise ConflictException(
                        message="Parent category is disabled",
                        code="CATEGORY_PARENT_DISABLED",
                    )

                if await self.repository.has_products(parent_id):
                    raise ConflictException(
                        message="Category already has products",
                        code="CATEGORY_HAS_PRODUCTS",
                    )

            return await self.repository.create(
                parent_id=parent_id,
                name=name.strip(),
                sort_order=sort_order,
            )

    async def update_category(
        self,
        category_id: int,
        *,
        name: str | None,
        sort_order: int | None,
        status: str | None,
    ) -> Category:
        async with self._transaction():
            snapshot = await self.repository.get_by_id(category_id)

            if snapshot is None:
                raise ResourceNotFoundException(
                    message="Category not found",
                    code="CATEGORY_NOT_FOUND",
                )

            lock_ids = [category_id]

            if status == "ENABLED" and snapshot.parent_id is not None:
                lock_ids.append(snapshot.parent_id)

            locked = await self.repository.get_by_ids_for_update(lock_ids)
            locked_by_id = {category.id: category for category in locked}
            category = locked_by_id.get(category_id)

            if category is None:
                raise ResourceNotFoundException(
                    message="Category not found",
                    code="CATEGORY_NOT_FOUND",
                )

            if status == "ENABLED" and category.parent_id is not None:
                parent = locked_by_id.get(category.parent_id)

                if parent is None:
                    raise ResourceNotFoundException(
                        message="Parent category not found",
                        code="CATEGORY_PARENT_NOT_FOUND",
                    )

                if parent.status != "ENABLED":
                    raise ConflictException(
                        message="Parent category is disabled",
                        code="CATEGORY_PARENT_DISABLED",
                    )

            if status == "DISABLED":
                if await self.repository.has_children(
                    category_id,
                    enabled_only=True,
                ):
                    raise ConflictException(
                        message="Category has enabled child categories",
                        code="CATEGORY_HAS_ENABLED_CHILDREN",
                    )

                if await self.repository.has_products(
                    category_id,
                    status="ACTIVE",
                ):
                    raise ConflictException(
                        message="Category has active products",
                        code="CATEGORY_HAS_ACTIVE_PRODUCTS",
                    )

            return await self.repository.update(
                category,
                name=name.strip() if name is not None else None,
                sort_order=sort_order,
                status=status,
            )

    async def get_category(self, category_id: int) -> Category:
        category = await self.repository.get_by_id(category_id)

        if category is None:
            raise ResourceNotFoundException(
                message="Category not found",
                code="CATEGORY_NOT_FOUND",
            )

        return category

    async def list_categories(self) -> list[Category]:
        return await self.repository.list_all()

    async def list_tree(self) -> list[CategoryTreeNode]:
        categories = await self.repository.list_all()
        nodes = {
            category.id: CategoryTreeNode.model_validate(category)
            for category in categories
        }
        roots: list[CategoryTreeNode] = []

        for category in categories:
            node = nodes[category.id]

            if category.parent_id is None:
                roots.append(node)
                continue

            parent = nodes.get(category.parent_id)

            if parent is not None:
                parent.children.append(node)

        return roots
