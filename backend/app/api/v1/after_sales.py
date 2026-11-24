"""售后 API.

用户侧接口负责申请, 查询, 取消和填写退货物流.
管理端接口负责审核, 收货和完成换货. 状态流转与退款规则由 AfterSaleService
统一控制, Router 只做协议转换.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentAdmin, CurrentUser
from app.api.v1.serializers import after_sale_response
from app.db.session import get_db
from app.repositories.order import OrderRepository
from app.repositories.order_item import OrderItemRepository
from app.schemas.after_sale import (
    AfterSaleApplyRequest,
    AfterSaleListResponse,
    AfterSaleRejectRequest,
    AfterSaleResponse,
    AfterSaleReviewRequest,
    CompleteExchangeRequest,
    ReturnShipmentRequest,
)
from app.services.after_sale import AfterSaleService

order_router = APIRouter()
router = APIRouter()
admin_router = APIRouter()


async def _response(
    session: AsyncSession,
    after_sale,
) -> AfterSaleResponse:
    """补充售后关联的订单和订单项信息, 统一生成响应."""
    order = await OrderRepository(session).get_by_id(after_sale.order_id)
    item = await OrderItemRepository(session).get_by_id(after_sale.order_item_id)
    if order is None or item is None:
        raise RuntimeError("After-sales relation is missing")
    return after_sale_response(after_sale, order=order, item=item)


@order_router.post(
    "/{order_no}/after-sales",
    response_model=AfterSaleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Apply for after-sales",
)
async def apply_after_sales(
    order_no: Annotated[str, Path(min_length=1, max_length=32)],
    request: AfterSaleApplyRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
) -> AfterSaleResponse:
    """对指定订单提交售后申请. 归属, 时间窗口和重复申请由 Service 校验."""
    service = AfterSaleService(session)
    after_sale = await service.apply(
        user_id=user.id,
        order_no=order_no,
        request=request,
    )
    return await _response(session, after_sale)


@order_router.get(
    "/{order_no}/after-sales",
    response_model=AfterSaleListResponse,
    summary="List my order after-sales",
)
async def list_order_after_sales(
    order_no: Annotated[str, Path(min_length=1, max_length=32)],
    session: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> AfterSaleListResponse:
    """分页查询指定订单的售后记录. 先校验订单归属再读取关联数据."""
    service = AfterSaleService(session)
    # Ownership is checked through the order before loading its requests.
    order = await OrderRepository(session).get_by_no(order_no)
    if order is None or order.user_id != user.id:
        from app.core.exceptions import ResourceNotFoundException

        raise ResourceNotFoundException(
            message="Order not found",
            code="ORDER_NOT_FOUND",
        )
    all_items = await service.after_sales.list_for_order(order.id)
    start = (page - 1) * page_size
    page_items = all_items[start : start + page_size]
    return AfterSaleListResponse(
        items=[await _response(session, item) for item in page_items],
        total=len(all_items),
        page=page,
        page_size=page_size,
    )


@router.get(
    "",
    response_model=AfterSaleListResponse,
    summary="List my after-sales requests",
)
async def list_my_after_sales(
    session: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> AfterSaleListResponse:
    service = AfterSaleService(session)
    items, total = await service.list_for_user(
        user_id=user.id,
        page=page,
        page_size=page_size,
    )
    return AfterSaleListResponse(
        items=[await _response(session, item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{after_sales_no}",
    response_model=AfterSaleResponse,
    summary="Get my after-sales request",
)
async def get_after_sales(
    after_sales_no: Annotated[str, Path(min_length=1, max_length=32)],
    session: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
) -> AfterSaleResponse:
    """查询当前用户的售后详情, 非本人记录按 404 处理."""
    service = AfterSaleService(session)
    after_sale = await service.get_for_user(
        user_id=user.id,
        after_sales_no=after_sales_no,
    )
    return await _response(session, after_sale)


@router.post(
    "/{after_sales_no}/cancel",
    response_model=AfterSaleResponse,
    summary="Cancel my pending after-sales request",
)
async def cancel_after_sales(
    after_sales_no: Annotated[str, Path(min_length=1, max_length=32)],
    session: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
) -> AfterSaleResponse:
    """取消仍处于待审核状态的售后申请."""
    service = AfterSaleService(session)
    after_sale = await service.cancel(
        user_id=user.id,
        after_sales_no=after_sales_no,
    )
    return await _response(session, after_sale)


@router.post(
    "/{after_sales_no}/return-shipment",
    response_model=AfterSaleResponse,
    summary="Submit return shipment information",
)
async def submit_return_shipment(
    after_sales_no: Annotated[str, Path(min_length=1, max_length=32)],
    request: ReturnShipmentRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
) -> AfterSaleResponse:
    """用户填写退货物流信息, 供管理端后续收货和验收."""
    service = AfterSaleService(session)
    after_sale = await service.submit_return_shipment(
        user_id=user.id,
        after_sales_no=after_sales_no,
        request=request,
    )
    return await _response(session, after_sale)


@admin_router.get(
    "",
    response_model=AfterSaleListResponse,
    summary="List all after-sales requests",
)
async def list_after_sales(
    session: Annotated[AsyncSession, Depends(get_db)],
    _admin: CurrentAdmin,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> AfterSaleListResponse:
    """管理员分页查询全部售后申请."""
    service = AfterSaleService(session)
    items, total = await service.list_admin(
        page=page,
        page_size=page_size,
        status=status_filter,
    )
    return AfterSaleListResponse(
        items=[await _response(session, item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@admin_router.get(
    "/{after_sales_no}",
    response_model=AfterSaleResponse,
    summary="Get an after-sales request",
)
async def get_after_sales_admin(
    after_sales_no: Annotated[str, Path(min_length=1, max_length=32)],
    session: Annotated[AsyncSession, Depends(get_db)],
    _admin: CurrentAdmin,
) -> AfterSaleResponse:
    """管理员查看任意售后详情."""
    service = AfterSaleService(session)
    after_sale = await service.get_admin(after_sales_no)
    return await _response(session, after_sale)


@admin_router.post(
    "/{after_sales_no}/approve",
    response_model=AfterSaleResponse,
    summary="Approve an after-sales request",
)
async def approve_after_sales(
    after_sales_no: Annotated[str, Path(min_length=1, max_length=32)],
    request: AfterSaleReviewRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    admin: CurrentAdmin,
) -> AfterSaleResponse:
    """管理员审核通过. 退款/换货的具体分支由 Service 根据售后类型决定."""
    service = AfterSaleService(session)
    after_sale = await service.approve(
        after_sales_no=after_sales_no,
        admin_id=admin.id,
        review_note=request.review_note,
    )
    return await _response(session, after_sale)


@admin_router.post(
    "/{after_sales_no}/reject",
    response_model=AfterSaleResponse,
    summary="Reject an after-sales request",
)
async def reject_after_sales(
    after_sales_no: Annotated[str, Path(min_length=1, max_length=32)],
    request: AfterSaleRejectRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    admin: CurrentAdmin,
) -> AfterSaleResponse:
    """管理员拒绝售后申请, 必须记录审核意见."""
    service = AfterSaleService(session)
    after_sale = await service.reject(
        after_sales_no=after_sales_no,
        admin_id=admin.id,
        review_note=request.review_note,
    )
    return await _response(session, after_sale)


@admin_router.post(
    "/{after_sales_no}/receive",
    response_model=AfterSaleResponse,
    summary="Receive returned goods",
)
async def receive_after_sales(
    after_sales_no: Annotated[str, Path(min_length=1, max_length=32)],
    session: Annotated[AsyncSession, Depends(get_db)],
    admin: CurrentAdmin,
) -> AfterSaleResponse:
    """管理员确认收到退货, 触发后续退款或换货流程."""
    service = AfterSaleService(session)
    after_sale = await service.receive(
        after_sales_no=after_sales_no,
        admin_id=admin.id,
    )
    return await _response(session, after_sale)


@admin_router.post(
    "/{after_sales_no}/complete-exchange",
    response_model=AfterSaleResponse,
    summary="Complete an exchange by shipping a replacement",
)
async def complete_exchange(
    after_sales_no: Annotated[str, Path(min_length=1, max_length=32)],
    request: CompleteExchangeRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    _admin: CurrentAdmin,
) -> AfterSaleResponse:
    """管理员完成换货, 记录新商品物流信息并结束售后."""
    service = AfterSaleService(session)
    after_sale = await service.complete_exchange(
        after_sales_no=after_sales_no,
        request=request,
    )
    return await _response(session, after_sale)
