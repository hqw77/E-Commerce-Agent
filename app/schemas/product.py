from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.sku import (
    SkuCreateRequest,
    SkuDetailResponse,
)


class ProductCreateRequest(BaseModel):
    """Payload for creating a product, optionally with nested SKUs."""

    model_config = ConfigDict(extra="forbid")

    product_no: str = Field(min_length=3, max_length=32)
    category_id: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    skus: list[SkuCreateRequest] = Field(default_factory=list)

    @field_validator("product_no", "name")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("Value must not be empty")

        return value


class ProductUpdateRequest(BaseModel):
    """Payload for updating product name, description or category."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    category_id: int | None = Field(default=None, ge=1)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        if value is None:
            return None

        value = value.strip()

        if not value:
            raise ValueError("Product name must not be empty")

        return value


class ProductResponse(BaseModel):
    """Product representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    product_no: str
    category_id: int
    name: str
    description: str | None
    status: str
    published_at: datetime | None
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ProductDetailResponse(ProductResponse):
    """Product representation with its SKUs and inventory summaries."""

    skus: list[SkuDetailResponse] = Field(default_factory=list)


class ProductListResponse(BaseModel):
    """Paginated product list."""

    items: list[ProductResponse]
    total: int
    page: int
    page_size: int


ProductStatus = Literal["DRAFT", "ACTIVE", "INACTIVE", "ARCHIVED"]
