"""Agent Tool 参数的严格 Pydantic Schema.

文件职责:
- 限制模型可以传入的工具参数.
- 通过 extra="forbid" 拒绝未知字段.
- 为 OpenAI function calling 提供 JSON Schema.

核心边界:
这些 Schema 只做结构校验; 权限和业务状态由 Tool handler 与 Service 校验.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# 订单查询允许的状态. 历史状态保留用于读取旧数据.
OrderStatus = Literal[
    "CREATED",
    "PENDING_PAYMENT",
    "PAID",
    "CANCELLED",
    "CLOSED",
    "COMPLETED",
]
# 当前售后只支持换货.
AfterSaleType = Literal["EXCHANGE"]


class _StrictToolInput(BaseModel):
    """所有 Tool 输入的共同基类: 禁止模型传入多余字段."""

    model_config = ConfigDict(extra="forbid")


class SearchProductsInput(_StrictToolInput):
    """商品关键词搜索参数."""

    query: str = Field(min_length=1, max_length=100)
    page: int = Field(default=1, ge=1, le=100)
    page_size: int = Field(default=10, ge=1, le=20)


class GetProductDetailInput(_StrictToolInput):
    """按商品编号查询详情."""

    product_no: str = Field(min_length=1, max_length=32)


class GetSkuDetailInput(_StrictToolInput):
    """按 SKU 编码查询规格详情."""

    sku_code: str = Field(min_length=1, max_length=64)


class CheckSkuInventoryInput(_StrictToolInput):
    """按 SKU 编码查询库存."""

    sku_code: str = Field(min_length=1, max_length=64)


class ListMyOrdersInput(_StrictToolInput):
    """查询当前用户订单列表."""

    status: OrderStatus | None = None
    page: int = Field(default=1, ge=1, le=100)
    page_size: int = Field(default=10, ge=1, le=20)


class GetMyOrderInput(_StrictToolInput):
    """查询当前用户的一笔订单."""

    order_no: str = Field(min_length=1, max_length=32)


class ListMyAfterSalesInput(_StrictToolInput):
    """查询当前用户售后列表."""

    order_no: str | None = Field(default=None, max_length=32)
    page: int = Field(default=1, ge=1, le=100)
    page_size: int = Field(default=10, ge=1, le=20)


class GetMyAfterSalesInput(_StrictToolInput):
    """查询当前用户的一笔售后记录."""

    after_sales_no: str = Field(min_length=1, max_length=32)


class PrepareCancelOrderInput(_StrictToolInput):
    """准备取消订单的输入."""

    order_no: str = Field(min_length=1, max_length=32)
    reason: str | None = Field(default=None, max_length=255)


class PrepareCreateAfterSaleInput(_StrictToolInput):
    """准备申请换货的输入."""

    order_no: str = Field(min_length=1, max_length=32)
    sku_code: str = Field(min_length=1, max_length=64)
    type: AfterSaleType
    reason: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    evidence_urls: list[str] | None = None


class PrepareAdjustInventoryInput(_StrictToolInput):
    """准备库存调整审批的输入."""

    sku_code: str = Field(min_length=1, max_length=64)
    quantity_delta: int = Field(ge=-100000, le=100000)
    reason: str = Field(min_length=1, max_length=255)
