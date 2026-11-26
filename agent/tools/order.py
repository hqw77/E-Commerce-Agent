"""订单和售后相关的 Agent Tool.

文件职责:
- 提供当前用户订单/售后的只读查询.
- 提供取消订单和申请售后的 PREPARE 工具.
- 把 ORM 结果转换成模型可读的字典.

核心边界:
查询必须按当前用户隔离; PREPARE 只生成确认记录, 不直接修改订单或售后.
"""

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
    """把可空 datetime 转成 ISO 字符串."""
    return value.isoformat() if value is not None else None


def _money(value: Decimal) -> str:
    """把 Decimal 金额转成字符串, 避免 JSON 浮点误差."""
    return str(value)


def _order_data(order) -> dict[str, Any]:
    """把 Order ORM 转成 Agent 可读的订单字典."""
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
    """把售后, 订单和订单项组合成模型可读的售后字典."""
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
    """查询当前用户订单列表, 支持状态和分页过滤."""
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
    """查询当前用户的一笔订单, 不暴露其他人的订单."""
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
    """查询当前用户售后列表, 可按订单号过滤."""
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
    """查询当前用户的一笔售后记录及其订单项."""
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
    """把 ConfirmationOffer 转成前端 PendingAction 结构."""
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
    """准备取消订单, 只创建 Redis 确认记录, 不直接取消."""
    args = PrepareCancelOrderInput.model_validate(raw_args.model_dump())
    order = await OrderService(context.session).get_order(
        user_id=context.user.id,
        order_no=args.order_no,
    )
    # ① 预检查当前状态; 真正取消时 Confirm 还会再次校验.
    if order.status != "CREATED":
        raise ConflictException(
            message="Only unshipped CREATED orders can be cancelled",
            code="ORDER_STATUS_CONFLICT",
        )
    # ② 生成一次性确认凭证, 业务写入留到 Confirm 阶段.
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
    """准备申请售后, 只创建 Redis 确认记录, 不直接创建售后."""
    args = PrepareCreateAfterSaleInput.model_validate(raw_args.model_dump())
    order = await OrderService(context.session).get_order(
        user_id=context.user.id,
        order_no=args.order_no,
    )
    # ① 先确认订单属于当前用户, 具体售后资格由 Confirm 阶段 Service 校验.
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
