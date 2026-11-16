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
    "/{after_sales_no}",
    response_model=AfterSaleResponse,
    summary="Get my after-sales request",
)
async def get_after_sales(
    after_sales_no: Annotated[str, Path(min_length=1, max_length=32)],
    session: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
) -> AfterSaleResponse:
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
    service = AfterSaleService(session)
    after_sale = await service.complete_exchange(
        after_sales_no=after_sales_no,
        request=request,
    )
    return await _response(session, after_sale)
