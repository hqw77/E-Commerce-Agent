"""管理端商品和 SKU API.

商品基础信息, 上下架/归档, SKU 创建和查询都在这里. 商品状态变化会直接影响
下单可用性, 因此全部由 ProductService/SkuService 做业务校验.
"""

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
    """创建 DRAFT 商品, 可同时创建嵌套 SKU. 创建后仍需显式上架."""
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
    """按状态, 分类和关键词分页查询商品."""
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
    """查询商品详情, 包含 SKU 和库存摘要."""
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
    """更新商品基础信息. 状态变更必须走独立的上下架/归档接口."""
    service = ProductService(session)
    await service.update_product(
        product_id,
        request,
        description_provided="description" in request.model_fields_set,
        image_url_provided="image_url" in request.model_fields_set,
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
    """上架 DRAFT/INACTIVE 商品, 使 SKU 可以被下单."""
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
    """下架 ACTIVE 商品, 阻止新的下单."""
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
    """归档商品. 归档后不应再参与正常销售."""
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
    """为商品创建 SKU, 同时初始化零库存记录."""
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
    """返回商品下的全部 SKU."""
    service = SkuService(session)
    skus = await service.list_skus(product_id)
    return [SkuResponse.model_validate(sku) for sku in skus]
