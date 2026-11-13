from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser
from app.api.v1.serializers import order_response, payment_response
from app.db.session import get_db
from app.schemas.order import (
    OrderCreateRequest,
    OrderListResponse,
    OrderResponse,
)
from app.schemas.payment import PaymentCreateRequest, PaymentResponse
from app.services.order import OrderService
from app.services.payment import PaymentService

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
    service = OrderService(session)
    order = await service.create_order(user_id=user.id, request=request)
    return order_response(order)


@router.get(
    "",
    response_model=OrderListResponse,
    summary="List my orders",
)
async def list_orders(
    session: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> OrderListResponse:
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
    service = OrderService(session)
    order = await service.get_order(user_id=user.id, order_no=order_no)
    return order_response(order)


@router.post(
    "/{order_no}/cancel",
    response_model=OrderResponse,
    summary="Cancel my pending order",
)
async def cancel_order(
    order_no: Annotated[str, Path(min_length=1, max_length=32)],
    session: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
    reason: Annotated[str | None, Query(max_length=255)] = None,
) -> OrderResponse:
    service = OrderService(session)
    order = await service.cancel_order(
        user_id=user.id,
        order_no=order_no,
        reason=reason,
    )
    return order_response(order)


@router.post(
    "/{order_no}/payments",
    response_model=PaymentResponse,
    summary="Create or get the order payment",
)
async def create_payment(
    order_no: Annotated[str, Path(min_length=1, max_length=32)],
    request: PaymentCreateRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
) -> PaymentResponse:
    service = PaymentService(session)
    payment, pay_url = await service.create_payment(
        user_id=user.id,
        order_no=order_no,
        request=request,
    )
    return payment_response(payment, pay_url=pay_url)
