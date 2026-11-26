"""消费者订单 API.

文件职责:
- 创建订单, 查询自己的订单, 取消未发货订单.
- 所有接口从 CurrentUser 获取身份, 不接受请求体中的 user_id.

边界:
当前没有支付接口; 订单创建后直接进入 CREATED/UNSHIPPED.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser
from app.api.v1.serializers import order_response
from app.db.session import get_db
from app.schemas.order import OrderCreateRequest, OrderListResponse, OrderResponse
from app.services.order import OrderService

router = APIRouter()


@router.post(
    "",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an order",
)
async def create_order(
    request: OrderCreateRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
) -> OrderResponse:
    """创建订单, 由 Service 负责库存预占和事务."""
    service = OrderService(session)
    order = await service.create_order(user_id=user.id, request=request)
    return order_response(order)


@router.get("", response_model=OrderListResponse, summary="List my orders")
async def list_orders(
    session: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> OrderListResponse:
    """分页查询当前用户订单."""
    service = OrderService(session)
    items, total = await service.list_orders(
        user_id=user.id,
        page=page,
        page_size=page_size,
        status=status_filter,
    )
    return OrderListResponse(
        items=[order_response(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{order_no}",
    response_model=OrderResponse,
    summary="Get my order",
)
async def get_order(
    order_no: Annotated[str, Path(min_length=1, max_length=32)],
    session: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
) -> OrderResponse:
    """按订单号查询当前用户订单, 越权时按不存在处理."""
    service = OrderService(session)
    order = await service.get_order(user_id=user.id, order_no=order_no)
    return order_response(order)


@router.post(
    "/{order_no}/cancel",
    response_model=OrderResponse,
    summary="Cancel my unshipped order",
)
async def cancel_order(
    order_no: Annotated[str, Path(min_length=1, max_length=32)],
    session: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
    reason: Annotated[str | None, Query(max_length=255)] = None,
) -> OrderResponse:
    """取消当前用户的未发货订单并释放库存预占."""
    service = OrderService(session)
    order = await service.cancel_order(
        user_id=user.id,
        order_no=order_no,
        reason=reason,
    )
    return order_response(order)
