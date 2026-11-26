"""消费者目录响应 Schema."""
from decimal import Decimal

from pydantic import BaseModel

from app.schemas.product import ProductDetailResponse


class CatalogProductResponse(BaseModel):
    """Public product-card representation for the storefront."""

    id: int
    product_no: str
    name: str
    description: str | None
    image_url: str | None
    category_id: int
    category_name: str
    price_from: Decimal | None
    price_to: Decimal | None
    sku_count: int
    available_stock: int
    total_stock: int


class CatalogProductListResponse(BaseModel):
    """目录商品分页响应."""
    items: list[CatalogProductResponse]
    total: int
    page: int
    page_size: int


class CatalogProductDetailResponse(ProductDetailResponse):
    """Public product detail with the display category name."""

    category_name: str
