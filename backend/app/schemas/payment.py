from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

PaymentChannel = Literal["MOCK", "ALIPAY"]
PaymentState = Literal[
    "PENDING",
    "SUCCESS",
    "FAILED",
    "CLOSED",
    "PARTIALLY_REFUNDED",
    "REFUNDED",
]


class PaymentCreateRequest(BaseModel):
    channel: PaymentChannel


class PaymentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    payment_no: str
    channel: PaymentChannel
    status: PaymentState
    amount: Decimal
    refunded_amount: Decimal
    exception_reason: str | None
    paid_at: datetime | None
    closed_at: datetime | None
    created_at: datetime
    pay_url: str | None = None


class PaymentListResponse(BaseModel):
    items: list[PaymentResponse]
    total: int
    page: int
    page_size: int


class MockPaymentResult(BaseModel):
    payment_no: str
    status: PaymentState
    order_status: str
    order_payment_status: str
    late_payment: bool = False


class ManualRefundRequest(BaseModel):
    payment_no: str = Field(min_length=1, max_length=32)
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    reason: str = Field(min_length=1, max_length=255)
    idempotency_key: str = Field(min_length=1, max_length=128)

    @field_validator("idempotency_key")
    @classmethod
    def validate_key(cls, value: str) -> str:
        if not value.isascii():
            raise ValueError("Idempotency key must be ASCII")
        return value


class RefundResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    refund_no: str
    status: str
    amount: Decimal
    reason: str
    channel: str
    after_sales_no: str | None = None
    failure_code: str | None
    failure_message: str | None
    requested_at: datetime
    processed_at: datetime | None
    created_at: datetime
