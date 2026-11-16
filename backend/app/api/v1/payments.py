from decimal import Decimal, InvalidOperation
from typing import Annotated, cast

from fastapi import APIRouter, Depends, Path, Query, Request, status
from fastapi.responses import PlainTextResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser
from app.api.v1.serializers import payment_response
from app.core.config import settings
from app.core.exceptions import ConflictException, ValidationException
from app.db.session import get_db
from app.repositories.order import OrderRepository
from app.schemas.payment import (
    MockPaymentResult,
    PaymentListResponse,
    PaymentResponse,
    PaymentState,
)
from app.services.alipay import AlipayClient
from app.services.payment import PaymentService

router = APIRouter()


@router.get(
    "",
    response_model=PaymentListResponse,
    summary="List my payments",
)
async def list_payments(
    session: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PaymentListResponse:
    service = PaymentService(session)
    items, total = await service.list_payments(
        user_id=user.id,
        page=page,
        page_size=page_size,
    )
    return PaymentListResponse(
        items=[payment_response(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{payment_no}",
    response_model=PaymentResponse,
    summary="Get my payment",
)
async def get_payment(
    payment_no: Annotated[str, Path(min_length=1, max_length=32)],
    session: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
) -> PaymentResponse:
    service = PaymentService(session)
    payment = await service.get_payment(
        user_id=user.id,
        payment_no=payment_no,
    )
    return payment_response(payment)


@router.post(
    "/{payment_no}/mock-success",
    response_model=MockPaymentResult,
    summary="Mock a successful payment",
)
async def mock_success(
    payment_no: Annotated[str, Path(min_length=1, max_length=32)],
    session: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
) -> MockPaymentResult:
    if settings.app_env == "production":
        raise ConflictException(
            message="MOCK payment is disabled in production",
            code="MOCK_PAYMENT_DISABLED",
        )
    service = PaymentService(session)
    payment, late = await service.mock_success(
        user_id=user.id,
        payment_no=payment_no,
    )
    order = await OrderRepository(session).get_by_id(payment.order_id)
    if order is None:
        raise ConflictException(
            message="Order not found",
            code="ORDER_NOT_FOUND",
        )
    return MockPaymentResult(
        payment_no=payment.payment_no,
        status=cast(PaymentState, payment.status),
        order_status=order.status,
        order_payment_status=order.payment_status,
        late_payment=late,
    )


@router.post(
    "/{payment_no}/mock-fail",
    response_model=PaymentResponse,
    summary="Mock a failed payment",
)
async def mock_fail(
    payment_no: Annotated[str, Path(min_length=1, max_length=32)],
    session: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
) -> PaymentResponse:
    if settings.app_env == "production":
        raise ConflictException(
            message="MOCK payment is disabled in production",
            code="MOCK_PAYMENT_DISABLED",
        )
    service = PaymentService(session)
    payment = await service.mock_fail(
        user_id=user.id,
        payment_no=payment_no,
    )
    return payment_response(payment)


@router.post(
    "/alipay/notify",
    response_class=PlainTextResponse,
    include_in_schema=True,
    summary="Alipay asynchronous notification",
)
async def alipay_notify(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> PlainTextResponse:
    form = await request.form()
    params = {key: str(value) for key, value in form.items()}
    client = AlipayClient()
    if not client.configured:
        return PlainTextResponse("failure", status_code=503)
    if not client.verify_notify(params):
        return PlainTextResponse("failure", status_code=status.HTTP_400_BAD_REQUEST)
    if not client.validate_notify_identity(params):
        return PlainTextResponse("failure", status_code=status.HTTP_400_BAD_REQUEST)
    if params.get("trade_status") not in {"TRADE_SUCCESS", "TRADE_FINISHED"}:
        return PlainTextResponse("success")

    try:
        amount = Decimal(params.get("total_amount", ""))
    except InvalidOperation:
        return PlainTextResponse("failure", status_code=status.HTTP_400_BAD_REQUEST)

    payment_no = params.get("out_trade_no")
    if not payment_no:
        return PlainTextResponse("failure", status_code=status.HTTP_400_BAD_REQUEST)

    try:
        await PaymentService(session).handle_alipay_success(
            payment_no=payment_no,
            amount=amount,
            provider_trade_no=params.get("trade_no"),
        )
    except (ConflictException, ValidationException):
        return PlainTextResponse("failure", status_code=status.HTTP_400_BAD_REQUEST)
    return PlainTextResponse("success")


@router.get(
    "/alipay/return",
    response_model=None,
    include_in_schema=True,
    summary="Alipay synchronous return page",
)
async def alipay_return() -> RedirectResponse | dict[str, str]:
    """Return page is informational; it never marks an order paid."""
    if settings.alipay_frontend_return_url:
        return RedirectResponse(settings.alipay_frontend_return_url)
    return {"message": "Payment result is confirmed asynchronously"}
