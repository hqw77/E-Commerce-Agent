from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SkuCreateRequest(BaseModel):
    """Payload for creating a SKU under a product."""

    model_config = ConfigDict(extra="forbid")

    sku_code: str = Field(min_length=1, max_length=64)
    attributes: dict[str, str]
    price: Decimal
    status: Literal["ACTIVE", "INACTIVE"] | None = None

    @field_validator("sku_code")
    @classmethod
    def normalize_sku_code(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("SKU code must not be empty")

        return value


class SkuUpdateRequest(BaseModel):
    """Payload for updating SKU price or status."""

    model_config = ConfigDict(extra="forbid")

    price: Decimal | None = None
    status: Literal["ACTIVE", "INACTIVE"] | None = None


class InventorySummary(BaseModel):
    """Compact inventory values shown with a SKU."""

    sku_id: int
    total_quantity: int
    reserved_quantity: int
    available_quantity: int


class SkuResponse(BaseModel):
    """SKU representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    sku_code: str
    attributes: dict[str, str]
    price: Decimal
    status: str
    created_at: datetime
    updated_at: datetime


class SkuDetailResponse(SkuResponse):
    """SKU representation including its inventory summary."""

    inventory: InventorySummary | None = None
