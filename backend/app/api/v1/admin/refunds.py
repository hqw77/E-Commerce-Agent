from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentAdmin
from app.api.v1.serializers import refund_response
from app.db.session import get_db
from app.repositories.after_sale import AfterSaleRepository
from app.schemas.payment import (
    ManualRefundRequest,
    RefundResponse,
)
from app.services.refund import RefundService

router = APIRouter()


async def _response(session: AsyncSession, refund) -> RefundResponse:
    after_sales_no = None
    if refund.after_sales_id is not None:
        after_sale = await AfterSaleRepository(session).get_by_id(refund.after_sales_id)
        if after_sale is not None:
            after_sales_no = after_sale.after_sales_no
    return refund_response(refund, after_sales_no=after_sales_no)


@router.post(
    "",
    response_model=RefundResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a manual refund",
)
async def create_refund(
    request: ManualRefundRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    _admin: CurrentAdmin,
) -> RefundResponse:
    service = RefundService(session)
    refund = await service.manual_refund(request=request)
    return await _response(session, refund)


@router.get(
    "",
    response_model=list[RefundResponse],
    summary="List refunds",
)
async def list_refunds(
    session: Annotated[AsyncSession, Depends(get_db)],
    _admin: CurrentAdmin,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[RefundResponse]:
    service = RefundService(session)
    items, _ = await service.list_refunds(
        page=page,
        page_size=page_size,
        status=status_filter,
    )
    return [await _response(session, item) for item in items]


@router.get(
    "/{refund_no}",
    response_model=RefundResponse,
    summary="Get a refund",
)
async def get_refund(
    refund_no: Annotated[str, Path(min_length=1, max_length=32)],
    session: Annotated[AsyncSession, Depends(get_db)],
    _admin: CurrentAdmin,
) -> RefundResponse:
    refund = await RefundService(session).get_refund(refund_no)
    return await _response(session, refund)


@router.post(
    "/{refund_no}/retry",
    response_model=RefundResponse,
    summary="Retry a failed refund",
)
async def retry_refund(
    refund_no: Annotated[str, Path(min_length=1, max_length=32)],
    session: Annotated[AsyncSession, Depends(get_db)],
    _admin: CurrentAdmin,
) -> RefundResponse:
    refund = await RefundService(session).retry(refund_no=refund_no)
    return await _response(session, refund)


@router.post(
    "/{refund_no}/sync",
    response_model=RefundResponse,
    summary="Query an unknown Alipay refund result",
)
async def sync_refund(
    refund_no: Annotated[str, Path(min_length=1, max_length=32)],
    session: Annotated[AsyncSession, Depends(get_db)],
    _admin: CurrentAdmin,
) -> RefundResponse:
    refund = await RefundService(session).sync_alipay_refund(refund_no=refund_no)
    return await _response(session, refund)
