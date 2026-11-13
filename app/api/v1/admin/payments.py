from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentAdmin
from app.api.v1.serializers import payment_response
from app.db.session import get_db
from app.schemas.payment import PaymentListResponse, PaymentResponse
from app.services.payment import PaymentService

router = APIRouter()


@router.get(
    "",
    response_model=PaymentListResponse,
    summary="List payments",
)
async def list_payments(
    session: Annotated[AsyncSession, Depends(get_db)],
    _admin: CurrentAdmin,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PaymentListResponse:
    service = PaymentService(session)
    items = await service.payments.list_admin(
        page=page,
        page_size=page_size,
        status=status_filter,
    )
    total = await service.payments.count_admin(status=status_filter)
    return PaymentListResponse(
        items=[payment_response(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{payment_no}",
    response_model=PaymentResponse,
    summary="Get a payment",
)
async def get_payment(
    payment_no: Annotated[str, Path(min_length=1, max_length=32)],
    session: Annotated[AsyncSession, Depends(get_db)],
    _admin: CurrentAdmin,
) -> PaymentResponse:
    service = PaymentService(session)
    payment = await service.payments.get_by_no(payment_no)
    if payment is None:
        from app.core.exceptions import ResourceNotFoundException

        raise ResourceNotFoundException(
            message="Payment not found",
            code="PAYMENT_NOT_FOUND",
        )
    return payment_response(payment)


@router.post(
    "/{payment_no}/sync",
    response_model=PaymentResponse,
    summary="Query the latest payment state",
)
async def sync_payment(
    payment_no: Annotated[str, Path(min_length=1, max_length=32)],
    session: Annotated[AsyncSession, Depends(get_db)],
    _admin: CurrentAdmin,
) -> PaymentResponse:
    """Query Alipay when configured, otherwise return local state."""
    service = PaymentService(session)
    payment = await service.sync_payment(payment_no=payment_no)
    return payment_response(payment)
