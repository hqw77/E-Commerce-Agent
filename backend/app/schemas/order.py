from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

OrderStatus = Literal[
    "PENDING_PAYMENT",
    "PAID",
    "CANCELLED",
    "CLOSED",
    "COMPLETED",
]
PaymentStatus = Literal[
    "UNPAID",
    "PAID",
    "PARTIALLY_REFUNDED",
    "REFUNDED",
]
FulfillmentStatus = Literal["UNSHIPPED", "SHIPPED", "DELIVERED", "COMPLETED"]


def _validate_idempotency_key(value: str) -> str:
    if not value.isascii():
        raise ValueError("Idempotency key must be ASCII")
    return value


class OrderItemCreateRequest(BaseModel):
    sku_code: str = Field(min_length=1, max_length=64)
    quantity: int = Field(ge=1, le=999)

    @field_validator("sku_code")
    @classmethod
    def normalize_sku_code(cls, value: str) -> str:
        return value.strip()


class OrderCreateRequest(BaseModel):
    items: list[OrderItemCreateRequest] = Field(min_length=1, max_length=50)
    receiver_name: str = Field(min_length=1, max_length=64)
    receiver_phone: str = Field(min_length=1, max_length=32)
    receiver_address: str = Field(min_length=1, max_length=500)
    customer_remark: str | None = Field(default=None, max_length=255)
    idempotency_key: str = Field(min_length=1, max_length=128)

    @field_validator("idempotency_key")
    @classmethod
    def validate_key(cls, value: str) -> str:
        return _validate_idempotency_key(value)

    @model_validator(mode="after")
    def reject_duplicate_skus(self) -> "OrderCreateRequest":
        sku_codes = [item.sku_code for item in self.items]
        if len(sku_codes) != len(set(sku_codes)):
            raise ValueError("Duplicate sku_code is not allowed")
        return self


class OrderItemResponse(BaseModel):
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
    model_config = ConfigDict(from_attributes=True)

    order_no: str
    status: OrderStatus
    payment_status: PaymentStatus
    fulfillment_status: FulfillmentStatus
    total_amount: Decimal
    paid_amount: Decimal
    refunded_amount: Decimal
    currency: str
    receiver_name: str
    receiver_phone: str
    receiver_address: str
    customer_remark: str | None
    shipping_carrier: str | None
    tracking_no: str | None
    expires_at: datetime
    paid_at: datetime | None
    shipped_at: datetime | None
    delivered_at: datetime | None
    completed_at: datetime | None
    cancelled_at: datetime | None
    closed_at: datetime | None
    created_at: datetime
    items: list[OrderItemResponse] = Field(default_factory=list)


class OrderListResponse(BaseModel):
    items: list[OrderResponse]
    total: int
    page: int
    page_size: int


class ShipOrderRequest(BaseModel):
    shipping_carrier: str = Field(min_length=1, max_length=64)
    tracking_no: str = Field(min_length=1, max_length=64)


class CompleteOrderResponse(BaseModel):
    order_no: str
    status: OrderStatus
    fulfillment_status: FulfillmentStatus
    completed_at: datetime | None


class CloseExpiredResponse(BaseModel):
    closed_count: int
