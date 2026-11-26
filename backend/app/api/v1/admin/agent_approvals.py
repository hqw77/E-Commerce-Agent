"""管理员 Agent 高风险审批 API.

文件职责:
- 列出和查看库存调整审批.
- 批准后执行原始计划.
- 拒绝后不执行任何业务写操作.

核心边界:
所有接口依赖 CurrentAdmin; 前端只提交 approval_id, 决定和备注.
"""

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
    """把 ORM 审批记录转换成 API 响应."""
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
    """按状态分页列出审批记录."""
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
    """返回一条审批详情."""
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
    """批准审批并执行服务端保存的原始计划."""
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
    """拒绝审批, 不执行业务写操作."""
    service = AgentApprovalService(session, admin, settings=get_settings())
    return _response(
        await service.reject(approval_id, review_note=request.review_note)
    )
