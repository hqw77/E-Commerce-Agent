"""售后请求/响应 Schema.

当前只允许 EXCHANGE; 历史退款类型仅用于读取."""
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Existing records may still carry the legacy REFUND types; current requests
# only accept EXCHANGE.
AfterSaleType = Literal["REFUND_ONLY", "RETURN_REFUND", "EXCHANGE"]
AfterSaleRequestType = Literal["EXCHANGE"]
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
    """用户换货申请参数."""
    sku_code: str = Field(min_length=1, max_length=64)
    type: AfterSaleRequestType
    reason: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    evidence_urls: list[str] | None = None
    idempotency_key: str = Field(min_length=1, max_length=128)

    @field_validator("idempotency_key")
    @classmethod
    def validate_key(cls, value: str) -> str:
        """校验并规范化幂等键."""
        if not value.isascii():
            raise ValueError("Idempotency key must be ASCII")
        return value


class AfterSaleResponse(BaseModel):
    """售后详情响应."""
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
    """售后分页响应."""
    items: list[AfterSaleResponse]
    total: int
    page: int
    page_size: int


class AfterSaleReviewRequest(BaseModel):
    """管理员审核通过参数."""
    review_note: str | None = Field(default=None, max_length=500)


class AfterSaleRejectRequest(BaseModel):
    """管理员拒绝参数."""
    review_note: str = Field(min_length=1, max_length=500)


class ReturnShipmentRequest(BaseModel):
    """用户退货物流参数."""
    return_carrier: str = Field(min_length=1, max_length=64)
    return_tracking_no: str = Field(min_length=1, max_length=64)


class CompleteExchangeRequest(BaseModel):
    """换货补发物流参数."""
    replacement_carrier: str = Field(min_length=1, max_length=64)
    replacement_tracking_no: str = Field(min_length=1, max_length=64)
