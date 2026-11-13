from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentAdmin
from app.api.v1.admin.validation import reject_duplicate_json_keys
from app.db.session import get_db
from app.schemas.product import (
    ProductCreateRequest,
    ProductDetailResponse,
    ProductListResponse,
    ProductStatus,
    ProductUpdateRequest,
)
from app.schemas.sku import SkuCreateRequest, SkuResponse
from app.services.product import ProductService
from app.services.sku import SkuService

router = APIRouter()


@router.post(
    "",
    response_model=ProductDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a product",
    dependencies=[Depends(reject_duplicate_json_keys)],
)
async def create_product(
    request: ProductCreateRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    _admin: CurrentAdmin,
) -> ProductDetailResponse:
    """Create a DRAFT product, optionally with nested SKUs."""
    service = ProductService(session)
    product = await service.create_product(request)
    return await service.get_product_detail(product.id)


@router.get(
    "",
    response_model=ProductListResponse,
    summary="List products",
)
async def list_products(
    session: Annotated[AsyncSession, Depends(get_db)],
    _admin: CurrentAdmin,
    status_filter: Annotated[
        ProductStatus | None,
        Query(alias="status"),
    ] = None,
    category_id: Annotated[int | None, Query(ge=1)] = None,
    keyword: Annotated[str | None, Query(max_length=200)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ProductListResponse:
    """List products with status/category/keyword filters and pagination."""
    service = ProductService(session)
    return await service.list_products(
        status=status_filter,
        category_id=category_id,
        keyword=keyword,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{product_id}",
    response_model=ProductDetailResponse,
    summary="Get product detail",
)
async def get_product(
    product_id: Annotated[int, Path(ge=1)],
    session: Annotated[AsyncSession, Depends(get_db)],
    _admin: CurrentAdmin,
) -> ProductDetailResponse:
    """Return a product with its SKUs and inventory summaries."""
    service = ProductService(session)
    return await service.get_product_detail(product_id)


@router.patch(
    "/{product_id}",
    response_model=ProductDetailResponse,
    summary="Update product basic information",
)
async def update_product(
    product_id: Annotated[int, Path(ge=1)],
    request: ProductUpdateRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    _admin: CurrentAdmin,
) -> ProductDetailResponse:
    """Update name, description or category; status uses dedicated routes."""
    service = ProductService(session)
    await service.update_product(
        product_id,
        request,
        description_provided="description" in request.model_fields_set,
    )
    return await service.get_product_detail(product_id)


@router.post(
    "/{product_id}/activate",
    response_model=ProductDetailResponse,
    summary="Activate a product",
)
async def activate_product(
    product_id: Annotated[int, Path(ge=1)],
    session: Annotated[AsyncSession, Depends(get_db)],
    _admin: CurrentAdmin,
) -> ProductDetailResponse:
    """Publish a DRAFT or INACTIVE product."""
    service = ProductService(session)
    await service.activate_product(product_id)
    return await service.get_product_detail(product_id)


@router.post(
    "/{product_id}/deactivate",
    response_model=ProductDetailResponse,
    summary="Deactivate a product",
)
async def deactivate_product(
    product_id: Annotated[int, Path(ge=1)],
    session: Annotated[AsyncSession, Depends(get_db)],
    _admin: CurrentAdmin,
) -> ProductDetailResponse:
    """Move an ACTIVE product to INACTIVE."""
    service = ProductService(session)
    await service.deactivate_product(product_id)
    return await service.get_product_detail(product_id)


@router.post(
    "/{product_id}/archive",
    response_model=ProductDetailResponse,
    summary="Archive a product",
)
async def archive_product(
    product_id: Annotated[int, Path(ge=1)],
    session: Annotated[AsyncSession, Depends(get_db)],
    _admin: CurrentAdmin,
) -> ProductDetailResponse:
    """Archive a non-archived product."""
    service = ProductService(session)
    await service.archive_product(product_id)
    return await service.get_product_detail(product_id)


@router.post(
    "/{product_id}/skus",
    response_model=SkuResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a SKU",
    dependencies=[Depends(reject_duplicate_json_keys)],
)
async def create_sku(
    product_id: Annotated[int, Path(ge=1)],
    request: SkuCreateRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    _admin: CurrentAdmin,
) -> SkuResponse:
    """Create a SKU and its zero-stock inventory row."""
    service = SkuService(session)
    sku = await service.create_sku(product_id, request)
    return SkuResponse.model_validate(sku)


@router.get(
    "/{product_id}/skus",
    response_model=list[SkuResponse],
    summary="List product SKUs",
)
async def list_skus(
    product_id: Annotated[int, Path(ge=1)],
    session: Annotated[AsyncSession, Depends(get_db)],
    _admin: CurrentAdmin,
) -> list[SkuResponse]:
    """Return all SKUs belonging to a product."""
    service = SkuService(session)
    skus = await service.list_skus(product_id)
    return [SkuResponse.model_validate(sku) for sku in skus]
