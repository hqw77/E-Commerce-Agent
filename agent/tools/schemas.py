"""Strict Pydantic v2 schemas for Agent tool arguments."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

OrderStatus = Literal[
    "CREATED",
    "PENDING_PAYMENT",
    "PAID",
    "CANCELLED",
    "CLOSED",
    "COMPLETED",
]
AfterSaleType = Literal["EXCHANGE"]


class _StrictToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SearchProductsInput(_StrictToolInput):
    query: str = Field(min_length=1, max_length=100)
    page: int = Field(default=1, ge=1, le=100)
    page_size: int = Field(default=10, ge=1, le=20)


class GetProductDetailInput(_StrictToolInput):
    product_no: str = Field(min_length=1, max_length=32)


class GetSkuDetailInput(_StrictToolInput):
    sku_code: str = Field(min_length=1, max_length=64)


class CheckSkuInventoryInput(_StrictToolInput):
    sku_code: str = Field(min_length=1, max_length=64)


class ListMyOrdersInput(_StrictToolInput):
    status: OrderStatus | None = None
    page: int = Field(default=1, ge=1, le=100)
    page_size: int = Field(default=10, ge=1, le=20)


class GetMyOrderInput(_StrictToolInput):
    order_no: str = Field(min_length=1, max_length=32)


class ListMyAfterSalesInput(_StrictToolInput):
    order_no: str | None = Field(default=None, max_length=32)
    page: int = Field(default=1, ge=1, le=100)
    page_size: int = Field(default=10, ge=1, le=20)


class GetMyAfterSalesInput(_StrictToolInput):
    after_sales_no: str = Field(min_length=1, max_length=32)


class PrepareCancelOrderInput(_StrictToolInput):
    order_no: str = Field(min_length=1, max_length=32)
    reason: str | None = Field(default=None, max_length=255)


class PrepareCreateAfterSaleInput(_StrictToolInput):
    order_no: str = Field(min_length=1, max_length=32)
    sku_code: str = Field(min_length=1, max_length=64)
    type: AfterSaleType
    reason: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    evidence_urls: list[str] | None = None


class PrepareAdjustInventoryInput(_StrictToolInput):
    sku_code: str = Field(min_length=1, max_length=64)
    quantity_delta: int = Field(ge=-100000, le=100000)
    reason: str = Field(min_length=1, max_length=255)
