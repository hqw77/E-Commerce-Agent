from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

AfterSaleType = Literal["REFUND_ONLY", "RETURN_REFUND", "EXCHANGE"]
AfterSaleStatus = Literal[
    "PENDING_REVIEW",
    "APPROVED",
    "REJECTED",
    "CANCELLED",
    "WAITING_RETURN",
    "RETURN_SHIPPED",
    "RECEIVED",
    "REFUNDING",
    "REFUND_FAILED",
    "COMPLETED",
]


class AfterSaleApplyRequest(BaseModel):
    sku_code: str = Field(min_length=1, max_length=64)
    type: AfterSaleType
    reason: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    evidence_urls: list[str] | None = None
    idempotency_key: str = Field(min_length=1, max_length=128)

    @field_validator("idempotency_key")
    @classmethod
    def validate_key(cls, value: str) -> str:
        if not value.isascii():
            raise ValueError("Idempotency key must be ASCII")
        return value


class AfterSaleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    after_sales_no: str
    order_no: str
    sku_code: str
    type: AfterSaleType
    status: AfterSaleStatus
    quantity: int
    requested_amount: Decimal
    approved_amount: Decimal | None
    reason: str
    description: str | None
    evidence_urls: list[str] | None
    review_note: str | None
    reviewed_at: datetime | None
    return_carrier: str | None
    return_tracking_no: str | None
    returned_at: datetime | None
    received_at: datetime | None
    replacement_carrier: str | None
    replacement_tracking_no: str | None
    replacement_shipped_at: datetime | None
    completed_at: datetime | None
    cancelled_at: datetime | None
    created_at: datetime


class AfterSaleListResponse(BaseModel):
    items: list[AfterSaleResponse]
    total: int
    page: int
    page_size: int


class AfterSaleReviewRequest(BaseModel):
    review_note: str | None = Field(default=None, max_length=500)


class AfterSaleRejectRequest(BaseModel):
    review_note: str = Field(min_length=1, max_length=500)


class ReturnShipmentRequest(BaseModel):
    return_carrier: str = Field(min_length=1, max_length=64)
    return_tracking_no: str = Field(min_length=1, max_length=64)


class CompleteExchangeRequest(BaseModel):
    replacement_carrier: str = Field(min_length=1, max_length=64)
    replacement_tracking_no: str = Field(min_length=1, max_length=64)
