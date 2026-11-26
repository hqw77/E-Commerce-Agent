"""库存操作请求/响应 Schema."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class InventoryOperationRequest(BaseModel):
    """Common fields for an inventory-changing request."""

    idempotency_key: str = Field(min_length=1, max_length=128)
    remark: str | None = Field(default=None, max_length=255)

    @field_validator("idempotency_key")
    @classmethod
    def validate_idempotency_key(cls, value: str) -> str:
        """校验幂等键非空且格式合法."""
        if not value.isascii():
            raise ValueError("Idempotency key must be ASCII")

        return value


class InventoryInitializeRequest(InventoryOperationRequest):
    """库存初始化参数."""
    initial_total: int


class StockInRequest(InventoryOperationRequest):
    """入库参数."""
    quantity: int


class StockOutRequest(InventoryOperationRequest):
    """出库参数."""
    quantity: int


class AdjustRequest(InventoryOperationRequest):
    """库存调整参数."""
    quantity_delta: int


class InventoryResponse(BaseModel):
    """Current inventory values for one SKU."""

    sku_id: int
    total_quantity: int
    reserved_quantity: int
    available_quantity: int


class InventoryTransactionResponse(BaseModel):
    """One inventory ledger entry."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    sku_id: int
    transaction_type: str
    total_delta: int
    reserved_delta: int
    total_after: int
    reserved_after: int
    business_type: str
    business_id: int | None
    business_item_id: int | None
    operator_id: int | None
    remark: str | None
    created_at: datetime


class InventoryOperationResponse(BaseModel):
    """Result of an inventory-changing operation."""

    transaction: InventoryTransactionResponse
    inventory: InventoryResponse


class InventoryTransactionListResponse(BaseModel):
    """Paginated inventory ledger entries."""

    items: list[InventoryTransactionResponse]
    total: int
    page: int
    page_size: int
