"""订单请求/响应 Schema.

新订单只使用 CREATED/CANCELLED/COMPLETED."""
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Legacy status values remain accepted for historical rows. New orders only use
# CREATED, CANCELLED and COMPLETED.
OrderStatus = Literal[
    "CREATED",
    "PENDING_PAYMENT",
    "PAID",
    "CANCELLED",
    "CLOSED",
    "COMPLETED",
]
FulfillmentStatus = Literal["UNSHIPPED", "SHIPPED", "DELIVERED", "COMPLETED"]


def _validate_idempotency_key(value: str) -> str:
    """校验并规范化订单幂等键."""
    if not value.isascii():
        raise ValueError("Idempotency key must be ASCII")
    return value


class OrderItemCreateRequest(BaseModel):
    """下单时的单个 SKU 参数."""
    sku_code: str = Field(min_length=1, max_length=64)
    quantity: int = Field(ge=1, le=999)

    @field_validator("sku_code")
    @classmethod
    def normalize_sku_code(cls, value: str) -> str:
        """规范化 SKU 编码."""
        return value.strip()


class OrderCreateRequest(BaseModel):
    """创建订单参数."""
    items: list[OrderItemCreateRequest] = Field(min_length=1, max_length=50)
    receiver_name: str = Field(min_length=1, max_length=64)
    receiver_phone: str = Field(min_length=1, max_length=32)
    receiver_address: str = Field(min_length=1, max_length=500)
    customer_remark: str | None = Field(default=None, max_length=255)
    idempotency_key: str = Field(min_length=1, max_length=128)

    @field_validator("idempotency_key")
    @classmethod
    def validate_key(cls, value: str) -> str:
        """校验订单幂等键."""
        return _validate_idempotency_key(value)

    @model_validator(mode="after")
    def reject_duplicate_skus(self) -> "OrderCreateRequest":
        """拒绝同一订单重复 SKU."""
        sku_codes = [item.sku_code for item in self.items]
        if len(sku_codes) != len(set(sku_codes)):
            raise ValueError("Duplicate sku_code is not allowed")
        return self


class OrderItemResponse(BaseModel):
    """订单项响应."""
    model_config = ConfigDict(from_attributes=True)

    sku_code: str
    product_no: str
    product_name: str
    sku_attributes: dict[str, str]
    currency: str
    unit_price: Decimal
    quantity: int
    line_amount: Decimal


class OrderResponse(BaseModel):
    """订单详情响应."""
    model_config = ConfigDict(from_attributes=True)

    order_no: str
    status: OrderStatus
    fulfillment_status: FulfillmentStatus
    total_amount: Decimal
    currency: str
    receiver_name: str
    receiver_phone: str
    receiver_address: str
    customer_remark: str | None
    shipping_carrier: str | None
    tracking_no: str | None
    shipped_at: datetime | None
    delivered_at: datetime | None
    completed_at: datetime | None
    cancelled_at: datetime | None
    created_at: datetime
    items: list[OrderItemResponse] = Field(default_factory=list)


class OrderListResponse(BaseModel):
    """订单分页响应."""
    items: list[OrderResponse]
    total: int
    page: int
    page_size: int


class ShipOrderRequest(BaseModel):
    """发货参数."""
    shipping_carrier: str = Field(min_length=1, max_length=64)
    tracking_no: str = Field(min_length=1, max_length=64)


class CompleteOrderResponse(BaseModel):
    """完成订单响应."""
    order_no: str
    status: OrderStatus
    fulfillment_status: FulfillmentStatus
    completed_at: datetime | None
