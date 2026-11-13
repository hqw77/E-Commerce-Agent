from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentAdmin
from app.api.v1.serializers import order_response
from app.db.session import get_db
from app.schemas.order import (
    CloseExpiredResponse,
    OrderListResponse,
    OrderResponse,
    ShipOrderRequest,
)
from app.services.order import OrderService

router = APIRouter()


@router.get(
    "",
    response_model=OrderListResponse,
    summary="List all orders",
)
async def list_orders(
    session: Annotated[AsyncSession, Depends(get_db)],
    _admin: CurrentAdmin,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> OrderListResponse:
    service = OrderService(session)
    items, total = await service.list_admin(
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
    summary="Get an order",
)
async def get_order(
    order_no: Annotated[str, Path(min_length=1, max_length=32)],
    session: Annotated[AsyncSession, Depends(get_db)],
    _admin: CurrentAdmin,
) -> OrderResponse:
    service = OrderService(session)
    order = await service.get_order_admin(order_no)
    return order_response(order)


@router.post(
    "/{order_no}/ship",
    response_model=OrderResponse,
    summary="Ship an order",
)
async def ship_order(
    order_no: Annotated[str, Path(min_length=1, max_length=32)],
    request: ShipOrderRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    _admin: CurrentAdmin,
) -> OrderResponse:
    service = OrderService(session)
    order = await service.ship(order_no=order_no, request=request)
    return order_response(order)


@router.post(
    "/{order_no}/deliver",
    response_model=OrderResponse,
    summary="Mark an order delivered",
)
async def deliver_order(
    order_no: Annotated[str, Path(min_length=1, max_length=32)],
    session: Annotated[AsyncSession, Depends(get_db)],
    _admin: CurrentAdmin,
) -> OrderResponse:
    service = OrderService(session)
    order = await service.deliver(order_no=order_no)
    return order_response(order)


@router.post(
    "/{order_no}/complete",
    response_model=OrderResponse,
    summary="Complete a delivered order",
)
async def complete_order(
    order_no: Annotated[str, Path(min_length=1, max_length=32)],
    session: Annotated[AsyncSession, Depends(get_db)],
    _admin: CurrentAdmin,
) -> OrderResponse:
    service = OrderService(session)
    order = await service.complete(order_no=order_no)
    return order_response(order)


@router.post(
    "/close-expired",
    response_model=CloseExpiredResponse,
    summary="Close expired pending orders",
)
async def close_expired_orders(
    session: Annotated[AsyncSession, Depends(get_db)],
    _admin: CurrentAdmin,
) -> CloseExpiredResponse:
    service = OrderService(session)
    return CloseExpiredResponse(closed_count=await service.close_expired_orders())
