import re
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    ConflictException,
    ResourceNotFoundException,
    ValidationException,
)
from app.models.category import Category
from app.models.product import Product
from app.repositories.category import CategoryRepository
from app.repositories.inventory import InventoryRepository
from app.repositories.product import ProductRepository
from app.repositories.sku import SkuRepository
from app.schemas.product import (
    ProductCreateRequest,
    ProductDetailResponse,
    ProductListResponse,
    ProductResponse,
    ProductUpdateRequest,
)
from app.schemas.sku import InventorySummary, SkuDetailResponse
from app.services.sku import create_sku_record
from app.services.transaction import transaction_context

PRODUCT_NO_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9_-]{2,31}$")


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class ProductService:
    """Business rules for products and their SKU collection."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = ProductRepository(session)
        self.category_repository = CategoryRepository(session)
        self.sku_repository = SkuRepository(session)
        self.inventory_repository = InventoryRepository(session)

    async def _validate_category(
        self,
        category_id: int,
        *,
        lock: bool,
    ) -> Category:
        category = await self.category_repository.get_by_id(
            category_id,
            for_update=lock,
        )

        if category is None:
            raise ResourceNotFoundException(
                message="Category not found",
                code="CATEGORY_NOT_FOUND",
            )

        if category.status != "ENABLED":
            raise ConflictException(
                message="Category is disabled",
                code="CATEGORY_DISABLED",
            )

        if await self.category_repository.has_children(category_id):
            raise ConflictException(
                message="Category is not a leaf category",
                code="CATEGORY_NOT_LEAF",
            )

        return category

    @staticmethod
    def _validate_product_no(product_no: str) -> None:
        if PRODUCT_NO_PATTERN.fullmatch(product_no) is None:
            raise ValidationException(
                message="Invalid product number format",
                code="INVALID_PRODUCT_NO",
            )

    @staticmethod
    def _is_product_no_conflict(exc: IntegrityError) -> bool:
        return "uq_products_product_no" in str(exc.orig)

    async def create_product(
        self,
        request: ProductCreateRequest,
    ) -> Product:
        async with transaction_context(self.session):
            await self._validate_category(
                request.category_id,
                lock=True,
            )
            self._validate_product_no(request.product_no)

            if await self.repository.get_by_product_no(request.product_no) is not None:
                raise ConflictException(
                    message="Product number already exists",
                    code="PRODUCT_NO_CONFLICT",
                )

            try:
                product = await self.repository.create(
                    product_no=request.product_no,
                    category_id=request.category_id,
                    name=request.name,
                    description=request.description,
                )
            except IntegrityError as exc:
                if self._is_product_no_conflict(exc):
                    raise ConflictException(
                        message="Product number already exists",
                        code="PRODUCT_NO_CONFLICT",
                    ) from exc
                raise

            for sku_request in request.skus:
                await create_sku_record(
                    self.session,
                    product,
                    sku_request,
                )

            return product

    async def get_product_detail(
        self,
        product_id: int,
    ) -> ProductDetailResponse:
        product = await self.repository.get_by_id(product_id)

        if product is None:
            raise ResourceNotFoundException(
                message="Product not found",
                code="PRODUCT_NOT_FOUND",
            )

        rows = await self.sku_repository.list_with_inventory(product_id)
        skus: list[SkuDetailResponse] = []

        for sku, inventory in rows:
            detail = SkuDetailResponse.model_validate(sku)

            if inventory is not None:
                detail.inventory = InventorySummary(
                    sku_id=sku.id,
                    total_quantity=inventory.total_quantity,
                    reserved_quantity=inventory.reserved_quantity,
                    available_quantity=(
                        inventory.total_quantity - inventory.reserved_quantity
                    ),
                )

            skus.append(detail)

        base = ProductResponse.model_validate(product)
        return ProductDetailResponse(
            **base.model_dump(),
            skus=skus,
        )

    async def list_products(
        self,
        *,
        status: str | None,
        category_id: int | None,
        keyword: str | None,
        page: int,
        page_size: int,
    ) -> ProductListResponse:
        items = await self.repository.list_products(
            status=status,
            category_id=category_id,
            keyword=keyword,
            page=page,
            page_size=page_size,
        )
        total = await self.repository.count(
            status=status,
            category_id=category_id,
            keyword=keyword,
        )

        return ProductListResponse(
            items=[ProductResponse.model_validate(product) for product in items],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def update_product(
        self,
        product_id: int,
        request: ProductUpdateRequest,
        *,
        description_provided: bool = False,
    ) -> Product:
        async with transaction_context(self.session):
            snapshot = await self.repository.get_by_id(product_id)

            if snapshot is None:
                raise ResourceNotFoundException(
                    message="Product not found",
                    code="PRODUCT_NOT_FOUND",
                )

            if snapshot.status == "ARCHIVED":
                raise ConflictException(
                    message="Archived product cannot be modified",
                    code="PRODUCT_ARCHIVED",
                )

            category_changed = (
                request.category_id is not None
                and request.category_id != snapshot.category_id
            )

            if category_changed:
                new_category_id = request.category_id
                assert new_category_id is not None

                if snapshot.status == "ACTIVE":
                    raise ConflictException(
                        message="Active product must be deactivated "
                        "before changing category",
                        code="PRODUCT_STATUS_CONFLICT",
                    )

                await self.category_repository.get_by_ids_for_update(
                    sorted(
                        {
                            snapshot.category_id,
                            new_category_id,
                        }
                    )
                )

                product = await self.repository.get_by_id(
                    product_id,
                    for_update=True,
                )

                if product is None:
                    raise ResourceNotFoundException(
                        message="Product not found",
                        code="PRODUCT_NOT_FOUND",
                    )

                if product.status == "ARCHIVED":
                    raise ConflictException(
                        message="Archived product cannot be modified",
                        code="PRODUCT_ARCHIVED",
                    )

                if product.status == "ACTIVE":
                    raise ConflictException(
                        message="Active product must be deactivated "
                        "before changing category",
                        code="PRODUCT_STATUS_CONFLICT",
                    )

                if product.category_id != snapshot.category_id:
                    raise ConflictException(
                        message="Product category changed concurrently",
                        code="PRODUCT_STATUS_CONFLICT",
                    )

                await self._validate_category(
                    new_category_id,
                    lock=False,
                )
                product.category_id = new_category_id
            else:
                product = await self.repository.get_by_id(
                    product_id,
                    for_update=True,
                )

                if product is None:
                    raise ResourceNotFoundException(
                        message="Product not found",
                        code="PRODUCT_NOT_FOUND",
                    )

                if product.status == "ARCHIVED":
                    raise ConflictException(
                        message="Archived product cannot be modified",
                        code="PRODUCT_ARCHIVED",
                    )

            if request.name is not None:
                product.name = request.name
            if description_provided:
                product.description = request.description

            return await self.repository.save(product)

    async def activate_product(self, product_id: int) -> Product:
        async with transaction_context(self.session):
            snapshot = await self.repository.get_by_id(product_id)

            if snapshot is None:
                raise ResourceNotFoundException(
                    message="Product not found",
                    code="PRODUCT_NOT_FOUND",
                )

            if snapshot.status == "ARCHIVED":
                raise ConflictException(
                    message="Archived product cannot be activated",
                    code="PRODUCT_ARCHIVED",
                )

            if snapshot.status not in {"DRAFT", "INACTIVE"}:
                raise ConflictException(
                    message="Product cannot be activated in its current state",
                    code="PRODUCT_STATUS_CONFLICT",
                )

            category_id = snapshot.category_id
            await self._validate_category(category_id, lock=True)

            product = await self.repository.get_by_id(
                product_id,
                for_update=True,
            )

            if product is None:
                raise ResourceNotFoundException(
                    message="Product not found",
                    code="PRODUCT_NOT_FOUND",
                )

            if product.category_id != category_id:
                raise ConflictException(
                    message="Product category changed concurrently",
                    code="PRODUCT_STATUS_CONFLICT",
                )

            if product.status == "ARCHIVED":
                raise ConflictException(
                    message="Archived product cannot be activated",
                    code="PRODUCT_ARCHIVED",
                )

            if product.status not in {"DRAFT", "INACTIVE"}:
                raise ConflictException(
                    message="Product cannot be activated in its current state",
                    code="PRODUCT_STATUS_CONFLICT",
                )

            sku_rows = await self.sku_repository.list_with_inventory(
                product_id,
                status="ACTIVE",
            )

            if not sku_rows:
                raise ConflictException(
                    message="Product has no active SKU",
                    code="PRODUCT_NOT_PUBLISHABLE",
                )

            for sku, inventory in sku_rows:
                if inventory is None or sku.price <= 0:
                    raise ConflictException(
                        message="Active SKU is not publishable",
                        code="PRODUCT_NOT_PUBLISHABLE",
                    )

            product.status = "ACTIVE"
            product.published_at = _utc_now()
            return await self.repository.save(product)

    async def deactivate_product(self, product_id: int) -> Product:
        async with transaction_context(self.session):
            product = await self.repository.get_by_id(
                product_id,
                for_update=True,
            )

            if product is None:
                raise ResourceNotFoundException(
                    message="Product not found",
                    code="PRODUCT_NOT_FOUND",
                )

            if product.status == "ARCHIVED":
                raise ConflictException(
                    message="Archived product cannot be deactivated",
                    code="PRODUCT_ARCHIVED",
                )

            if product.status != "ACTIVE":
                raise ConflictException(
                    message="Only active products can be deactivated",
                    code="PRODUCT_STATUS_CONFLICT",
                )

            product.status = "INACTIVE"
            return await self.repository.save(product)

    async def archive_product(self, product_id: int) -> Product:
        async with transaction_context(self.session):
            product = await self.repository.get_by_id(
                product_id,
                for_update=True,
            )

            if product is None:
                raise ResourceNotFoundException(
                    message="Product not found",
                    code="PRODUCT_NOT_FOUND",
                )

            if product.status == "ARCHIVED":
                raise ConflictException(
                    message="Product is already archived",
                    code="PRODUCT_ARCHIVED",
                )

            product.status = "ARCHIVED"
            product.archived_at = _utc_now()
            return await self.repository.save(product)
