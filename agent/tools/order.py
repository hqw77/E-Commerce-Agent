"""Read-only order and after-sales tools plus Prepare tools."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from app.core.exceptions import ConflictException
from app.services.after_sale import AfterSaleService
from app.services.order import OrderService
from pydantic import BaseModel

from agent.tools.context import ToolContext
from agent.tools.errors import ToolResult
from agent.tools.schemas import (
    GetMyAfterSalesInput,
    GetMyOrderInput,
    ListMyAfterSalesInput,
    ListMyOrdersInput,
    PrepareCancelOrderInput,
    PrepareCreateAfterSaleInput,
)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _money(value: Decimal) -> str:
    return str(value)


def _order_data(order) -> dict[str, Any]:
    return {
        "order_no": order.order_no,
        "status": order.status,
        "fulfillment_status": order.fulfillment_status,
        "total_amount": _money(order.total_amount),
        "currency": order.currency,
        "created_at": _iso(order.created_at),
        "shipped_at": _iso(order.shipped_at),
        "delivered_at": _iso(order.delivered_at),
        "cancelled_at": _iso(order.cancelled_at),
        "shipping_carrier": order.shipping_carrier,
        "tracking_no": order.tracking_no,
        "items": [
            {
                "sku_code": item.sku_code,
                "product_no": item.product_no,
                "product_name": item.product_name,
                "sku_attributes": item.sku_attributes,
                "unit_price": _money(item.unit_price),
                "quantity": item.quantity,
                "line_amount": _money(item.line_amount),
            }
            for item in order.items
        ],
    }


def _after_sale_data(after_sale, order, item) -> dict[str, Any]:
    return {
        "after_sales_no": after_sale.after_sales_no,
        "order_no": order.order_no,
        "sku_code": item.sku_code,
        "type": after_sale.type,
        "status": after_sale.status,
        "quantity": after_sale.quantity,
        "reason": after_sale.reason,
        "description": after_sale.description,
        "created_at": _iso(after_sale.created_at),
        "completed_at": _iso(after_sale.completed_at),
    }


async def list_my_orders(
    context: ToolContext,
    raw_args: BaseModel,
) -> ToolResult:
    args = ListMyOrdersInput.model_validate(raw_args.model_dump())
    items, total = await OrderService(context.session).list_orders(
        user_id=context.user.id,
        page=args.page,
        page_size=args.page_size,
        status=args.status,
    )
    return ToolResult(
        ok=True,
        tool="list_my_orders",
        data={
            "items": [_order_data(order) for order in items],
            "total": total,
            "page": args.page,
        },
    )


async def get_my_order(
    context: ToolContext,
    raw_args: BaseModel,
) -> ToolResult:
    args = GetMyOrderInput.model_validate(raw_args.model_dump())
    order = await OrderService(context.session).get_order(
        user_id=context.user.id,
        order_no=args.order_no,
    )
    return ToolResult(ok=True, tool="get_my_order", data=_order_data(order))


async def list_my_after_sales(
    context: ToolContext,
    raw_args: BaseModel,
) -> ToolResult:
    args = ListMyAfterSalesInput.model_validate(raw_args.model_dump())
    service = AfterSaleService(context.session)
    if args.order_no:
        items, total = await service.list_for_order_for_user(
            user_id=context.user.id,
            order_no=args.order_no,
            page=args.page,
            page_size=args.page_size,
        )
    else:
        items, total = await service.list_for_user(
            user_id=context.user.id,
            page=args.page,
            page_size=args.page_size,
        )
    data = []
    for item in items:
        _after_sale, order, order_item = await service.get_with_relations_for_user(
            user_id=context.user.id,
            after_sales_no=item.after_sales_no,
        )
        data.append(_after_sale_data(_after_sale, order, order_item))
    return ToolResult(
        ok=True,
        tool="list_my_after_sales",
        data={"items": data, "total": total, "page": args.page},
    )


async def get_my_after_sales(
    context: ToolContext,
    raw_args: BaseModel,
) -> ToolResult:
    args = GetMyAfterSalesInput.model_validate(raw_args.model_dump())
    after_sale, order, item = await AfterSaleService(
        context.session
    ).get_with_relations_for_user(
        user_id=context.user.id,
        after_sales_no=args.after_sales_no,
    )
    return ToolResult(
        ok=True,
        tool="get_my_after_sales",
        data=_after_sale_data(after_sale, order, item),
    )


def _offer(
    offer,
    *,
    title: str,
    effect: str,
) -> dict[str, Any]:
    return {
        "confirmation_id": offer.confirmation_id,
        "nonce": offer.nonce,
        "conversation_id": str(offer.conversation_id),
        "action_type": offer.operation,
        "title": title,
        "resource_no": offer.resource_no,
        "effect": effect,
        "summary": offer.summary,
        "expires_at": datetime.fromtimestamp(offer.expires_at, UTC).isoformat(),
    }


async def prepare_cancel_order(
    context: ToolContext,
    raw_args: BaseModel,
) -> ToolResult:
    args = PrepareCancelOrderInput.model_validate(raw_args.model_dump())
    order = await OrderService(context.session).get_order(
        user_id=context.user.id,
        order_no=args.order_no,
    )
    if order.status != "CREATED":
        raise ConflictException(
            message="Only unshipped CREATED orders can be cancelled",
            code="ORDER_STATUS_CONFLICT",
        )
    offer = await context.confirmation_store.create(
        user_id=context.user.id,
        conversation_id=context.conversation_id,
        operation="CANCEL_ORDER",
        tool_name="prepare_cancel_order",
        resource_no=order.order_no,
        arguments={"order_no": order.order_no, "reason": args.reason},
        summary=f"取消订单 {order.order_no}，释放该订单的预占库存。",
    )
    return ToolResult(
        ok=True,
        tool="prepare_cancel_order",
        data={"confirmation_required": True},
        pending_action=_offer(
            offer,
            title="取消订单",
            effect="取消订单并释放预占库存",
        ),
    )


async def prepare_create_after_sales(
    context: ToolContext,
    raw_args: BaseModel,
) -> ToolResult:
    args = PrepareCreateAfterSaleInput.model_validate(raw_args.model_dump())
    order = await OrderService(context.session).get_order(
        user_id=context.user.id,
        order_no=args.order_no,
    )
    offer = await context.confirmation_store.create(
        user_id=context.user.id,
        conversation_id=context.conversation_id,
        operation="APPLY_AFTER_SALE",
        tool_name="prepare_create_after_sales",
        resource_no=order.order_no,
        arguments={
            "order_no": order.order_no,
            "sku_code": args.sku_code,
            "type": args.type,
            "reason": args.reason,
            "description": args.description,
            "evidence_urls": args.evidence_urls,
        },
        summary=f"为订单 {order.order_no} 的 {args.sku_code} 提交售后申请。",
    )
    return ToolResult(
        ok=True,
        tool="prepare_create_after_sales",
        data={"confirmation_required": True},
        pending_action=_offer(
            offer,
            title="申请售后",
            effect="提交售后申请，审核结果以售后记录为准",
        ),
    )
