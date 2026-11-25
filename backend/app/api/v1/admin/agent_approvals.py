"""Administrator API for high-risk Agent approvals."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentAdmin
from app.core.config import get_settings
from app.db.session import get_db
from app.schemas.agent_approval import (
    AgentApprovalDecisionRequest,
    AgentApprovalListResponse,
    AgentApprovalResponse,
    ApprovalStatus,
)
from app.services.agent_approval import AgentApprovalService

router = APIRouter()


def _response(record) -> AgentApprovalResponse:
    return AgentApprovalResponse.model_validate(record)


@router.get(
    "",
    response_model=AgentApprovalListResponse,
    summary="List Agent high-risk approvals",
)
async def list_approvals(
    session: Annotated[AsyncSession, Depends(get_db)],
    admin: CurrentAdmin,
    status: Annotated[ApprovalStatus | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> AgentApprovalListResponse:
    service = AgentApprovalService(session, admin, settings=get_settings())
    items, total = await service.list_approvals(
        status=status,
        page=page,
        page_size=page_size,
    )
    return AgentApprovalListResponse(
        items=[_response(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{approval_id}",
    response_model=AgentApprovalResponse,
    summary="Get one Agent approval",
)
async def get_approval(
    approval_id: Annotated[str, Path(min_length=1, max_length=64)],
    session: Annotated[AsyncSession, Depends(get_db)],
    admin: CurrentAdmin,
) -> AgentApprovalResponse:
    service = AgentApprovalService(session, admin, settings=get_settings())
    return _response(await service.get(approval_id))


@router.post(
    "/{approval_id}/approve",
    response_model=AgentApprovalResponse,
    summary="Approve and execute an Agent plan",
)
async def approve(
    approval_id: Annotated[str, Path(min_length=1, max_length=64)],
    request: AgentApprovalDecisionRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    admin: CurrentAdmin,
) -> AgentApprovalResponse:
    service = AgentApprovalService(session, admin, settings=get_settings())
    return _response(
        await service.approve(approval_id, review_note=request.review_note)
    )


@router.post(
    "/{approval_id}/reject",
    response_model=AgentApprovalResponse,
    summary="Reject an Agent plan",
)
async def reject(
    approval_id: Annotated[str, Path(min_length=1, max_length=64)],
    request: AgentApprovalDecisionRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    admin: CurrentAdmin,
) -> AgentApprovalResponse:
    service = AgentApprovalService(session, admin, settings=get_settings())
    return _response(
        await service.reject(approval_id, review_note=request.review_note)
    )
