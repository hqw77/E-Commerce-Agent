import hashlib
import json
import unicodedata
from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    ConflictException,
    ResourceNotFoundException,
    ValidationException,
)
from app.models.product import Product
from app.models.sku import Sku
from app.repositories.inventory import InventoryRepository
from app.repositories.product import ProductRepository
from app.repositories.sku import SkuRepository
from app.schemas.sku import SkuCreateRequest
from app.services.transaction import transaction_context


def _ascii_lower(value: str) -> str:
    return "".join(
        chr(ord(character) + 32) if "A" <= character <= "Z" else character
        for character in value
    )


def normalize_attributes(
    attributes: dict[str, str],
) -> tuple[dict[str, str], str, str]:
    """Normalize SKU attributes and return canonical JSON plus its hash."""
    if not attributes:
        raise ValidationException(
            message="SKU attributes must not be empty",
            code="SKU_ATTRIBUTES_INVALID",
        )

    normalized: dict[str, str] = {}

    for raw_key, raw_value in attributes.items():
        key = _ascii_lower(unicodedata.normalize("NFC", raw_key).strip())
        value = unicodedata.normalize("NFC", raw_value).strip()

        if not 1 <= len(key) <= 32:
            raise ValidationException(
                message="SKU attribute key length is invalid",
                code="SKU_ATTRIBUTES_INVALID",
            )

        if len(value) > 64:
            raise ValidationException(
                message="SKU attribute value is too long",
                code="SKU_ATTRIBUTES_INVALID",
            )

        if key in normalized:
            raise ValidationException(
                message="SKU attributes contain duplicate keys",
                code="SKU_ATTRIBUTES_INVALID",
            )

        normalized[key] = value

    canonical_json = json.dumps(
        normalized,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    attributes_hash = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

    return normalized, canonical_json, attributes_hash


def _constraint_name_in_error(exc: IntegrityError, name: str) -> bool:
    return name in str(exc.orig)


async def create_sku_record(
    session: AsyncSession,
    product: Product,
    request: SkuCreateRequest,
) -> Sku:
    """Create a SKU and its zero-stock inventory row in one transaction."""
    if request.price <= Decimal(0):
        raise ValidationException(
            message="SKU price must be greater than zero",
            code="INVALID_PRICE",
        )

    normalized, _canonical_json, attributes_hash = normalize_attributes(
        request.attributes
    )
    repository = SkuRepository(session)
    inventory_repository = InventoryRepository(session)

    if await repository.get_by_code(request.sku_code) is not None:
        raise ConflictException(
            message="SKU code already exists",
            code="SKU_CODE_CONFLICT",
        )

    existing = await repository.get_by_product_hash(
        product_id=product.id,
        attributes_hash=attributes_hash,
    )

    if existing is not None:
        raise ConflictException(
            message="SKU attributes already exist for this product",
            code="SKU_ATTRIBUTES_CONFLICT",
        )

    try:
        sku = await repository.create(
            product_id=product.id,
            sku_code=request.sku_code,
            attributes=normalized,
            attributes_hash=attributes_hash,
            price=request.price,
            status=request.status or "ACTIVE",
        )
    except IntegrityError as exc:
        if _constraint_name_in_error(exc, "uq_skus_sku_code"):
            raise ConflictException(
                message="SKU code already exists",
                code="SKU_CODE_CONFLICT",
            ) from exc

        if _constraint_name_in_error(exc, "uq_skus_product_attributes"):
            raise ConflictException(
                message="SKU attributes already exist for this product",
                code="SKU_ATTRIBUTES_CONFLICT",
            ) from exc

        raise

    await inventory_repository.create(sku_id=sku.id)
    return sku


class SkuService:
    """Business rules for SKU creation and updates."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.product_repository = ProductRepository(session)
        self.repository = SkuRepository(session)

    async def create_sku(
        self,
        product_id: int,
        request: SkuCreateRequest,
    ) -> Sku:
        async with transaction_context(self.session):
            product = await self.product_repository.get_by_id(
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

            return await create_sku_record(
                self.session,
                product,
                request,
            )

    async def list_skus(self, product_id: int) -> list[Sku]:
        product = await self.product_repository.get_by_id(product_id)

        if product is None:
            raise ResourceNotFoundException(
                message="Product not found",
                code="PRODUCT_NOT_FOUND",
            )

        return await self.repository.list_by_product(product_id)

    async def update_sku(
        self,
        sku_id: int,
        *,
        price: Decimal | None,
        status: str | None,
    ) -> Sku:
        async with transaction_context(self.session):
            snapshot = await self.repository.get_by_id(sku_id)

            if snapshot is None:
                raise ResourceNotFoundException(
                    message="SKU not found",
                    code="SKU_NOT_FOUND",
                )

            product = await self.product_repository.get_by_id(
                snapshot.product_id,
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

            sku = await self.repository.get_by_id(
                sku_id,
                for_update=True,
            )

            if sku is None:
                raise ResourceNotFoundException(
                    message="SKU not found",
                    code="SKU_NOT_FOUND",
                )

            if price is not None and price <= Decimal(0):
                raise ValidationException(
                    message="SKU price must be greater than zero",
                    code="INVALID_PRICE",
                )

            if price is not None:
                sku.price = price
            if status is not None:
                sku.status = status

            return await self.repository.save(sku)
