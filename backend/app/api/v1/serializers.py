"""API response assembly for orders and after-sales records."""

from typing import cast

from app.models.after_sale import AfterSale
from app.models.order import Order
from app.models.order_item import OrderItem
from app.schemas.after_sale import (
    AfterSaleResponse,
    AfterSaleStatus,
    AfterSaleType,
)
from app.schemas.order import OrderResponse


def order_response(order: Order) -> OrderResponse:
    return OrderResponse.model_validate(order)


def after_sale_response(
    after_sale: AfterSale,
    *,
    order: Order,
    item: OrderItem,
) -> AfterSaleResponse:
    return AfterSaleResponse(
        after_sales_no=after_sale.after_sales_no,
        order_no=order.order_no,
        sku_code=item.sku_code,
        type=cast(AfterSaleType, after_sale.type),
        status=cast(AfterSaleStatus, after_sale.status),
        quantity=after_sale.quantity,
        requested_amount=after_sale.requested_amount,
        approved_amount=after_sale.approved_amount,
        reason=after_sale.reason,
        description=after_sale.description,
        evidence_urls=after_sale.evidence_urls,
        review_note=after_sale.review_note,
        reviewed_at=after_sale.reviewed_at,
        return_carrier=after_sale.return_carrier,
        return_tracking_no=after_sale.return_tracking_no,
        returned_at=after_sale.returned_at,
        received_at=after_sale.received_at,
        replacement_carrier=after_sale.replacement_carrier,
        replacement_tracking_no=after_sale.replacement_tracking_no,
        replacement_shipped_at=after_sale.replacement_shipped_at,
        completed_at=after_sale.completed_at,
        cancelled_at=after_sale.cancelled_at,
        created_at=after_sale.created_at,
    )
