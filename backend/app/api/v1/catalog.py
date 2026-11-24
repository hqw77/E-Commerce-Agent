from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.catalog import (
    CatalogProductDetailResponse,
    CatalogProductListResponse,
    CatalogProductResponse,
)
from app.schemas.category import CategoryResponse
from app.services.category import CategoryService
from app.services.product import ProductService

router = APIRouter()


@router.get(
    "/categories",
    response_model=list[CategoryResponse],
    summary="List public categories",
)
async def list_catalog_categories(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[CategoryResponse]:
    categories = await CategoryService(session).list_categories()
    return [
        CategoryResponse.model_validate(category)
        for category in categories
        if category.status == "ENABLED"
    ]


@router.get(
    "/products",
    response_model=CatalogProductListResponse,
    summary="Browse active products",
)
async def list_catalog_products(
    session: Annotated[AsyncSession, Depends(get_db)],
    category_id: Annotated[int | None, Query(ge=1)] = None,
    keyword: Annotated[str | None, Query(max_length=200)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 20,
) -> CatalogProductListResponse:
    product_service = ProductService(session)
    result = await product_service.list_products(
        status="ACTIVE",
        category_id=category_id,
        keyword=keyword,
        page=page,
        page_size=page_size,
    )
    categories = await CategoryService(session).list_categories()
    category_names = {category.id: category.name for category in categories}

    items: list[CatalogProductResponse] = []
    for product in result.items:
        detail = await product_service.get_product_detail(product.id)
        active_skus = [sku for sku in detail.skus if sku.status == "ACTIVE"]
        prices = [sku.price for sku in active_skus]
        available_stock = sum(
            sku.inventory.available_quantity
            for sku in active_skus
            if sku.inventory is not None
        )
        total_stock = sum(
            sku.inventory.total_quantity
            for sku in active_skus
            if sku.inventory is not None
        )
        items.append(
            CatalogProductResponse(
                id=product.id,
                product_no=product.product_no,
                name=product.name,
                description=product.description,
                image_url=product.image_url,
                category_id=product.category_id,
                category_name=category_names.get(product.category_id, "未分类"),
                price_from=min(prices) if prices else None,
                price_to=max(prices) if prices else None,
                sku_count=len(active_skus),
                available_stock=available_stock,
                total_stock=total_stock,
            )
        )

    return CatalogProductListResponse(
        items=items,
        total=result.total,
        page=result.page,
        page_size=result.page_size,
    )


@router.get(
    "/products/{product_no}",
    response_model=CatalogProductDetailResponse,
    summary="Get an active product by product number",
)
async def get_catalog_product(
    product_no: Annotated[str, Path(min_length=1, max_length=32)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> CatalogProductDetailResponse:
    product_service = ProductService(session)
    detail = await product_service.get_product_detail_by_no(product_no)
    categories = await CategoryService(session).list_categories()
    category_name = next(
        (category.name for category in categories if category.id == detail.category_id),
        "未分类",
    )
    return CatalogProductDetailResponse(
        **detail.model_dump(),
        category_name=category_name,
    )
