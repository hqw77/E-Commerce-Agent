"""Agent chat, Trace 查询和确认执行 API.

这一层不承载 Agent 业务规则, 只负责创建运行时, 组装响应和把 Confirm
请求交给 ConfirmationService. Agent 的真正执行边界在 agent/ 包内.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path
from sqlalchemy.ext.asyncio import AsyncSession

from agent.observability.store import get_trace_buffer
from agent.runtime import AgentRuntime
from agent.tools.confirmation import ConfirmationService
from app.api.dependencies import CurrentDebugger, CurrentUser
from app.core.config import get_settings
from app.core.exceptions import ResourceNotFoundException
from app.db.session import get_db
from app.schemas.agent import (
    ChatRequest,
    ChatResponse,
    ConfirmActionRequest,
    ConfirmActionResponse,
    PendingActionResponse,
    SourceResponse,
    TraceEventResponse,
    TraceRunResponse,
)
from app.schemas.agent_approval import (
    AgentApprovalListResponse,
    AgentApprovalResponse,
    ApprovalStatus,
)
from app.services.agent_approval import AgentApprovalService

router = APIRouter()


@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="Chat with the E-Commerce Agent",
)
async def chat(
    request: ChatRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
) -> ChatResponse:
    """接收用户消息并执行一次 Agent 请求.

    Args:
        request: 消息和可选会话 ID.
        session: 当前请求数据库会话.
        user: CurrentUser 注入的可信用户.

    Returns:
        ChatResponse, 包含回答, 来源和 pending_action.
    """
    runtime = AgentRuntime(
        session=session,
        user=user,
        settings=get_settings(),
    )
    result = await runtime.chat(
        message=request.message,
        conversation_id=request.conversation_id,
    )
    return ChatResponse(
        conversation_id=result.conversation_id,
        message_id=result.message_id,
        answer=result.answer,
        sources=[
            SourceResponse(
                document_id=source.document_id,
                version_id=source.version_id,
                chunk_id=source.chunk_id,
                title=source.title,
                section_title=source.section_title,
                page_number=source.page_number,
            )
            for source in result.sources
        ],
        pending_action=(
            PendingActionResponse.model_validate(result.pending_action)
            if result.pending_action
            else None
        ),
        created_at=result.created_at,
        trace_id=result.trace_id,
    )


@router.get(
    "/approvals/mine",
    response_model=AgentApprovalListResponse,
    summary="List my Agent approvals",
)
async def list_my_approvals(
    session: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
    status: ApprovalStatus | None = None,
    page: int = 1,
    page_size: int = 20,
) -> AgentApprovalListResponse:
    """查询当前用户自己发起的审批, 不暴露其他人的记录."""
    service = AgentApprovalService(session, user, settings=get_settings())
    items, total = await service.list_for_requester(
        requester_id=user.id,
        status=status,
        page=page,
        page_size=page_size,
    )
    return AgentApprovalListResponse(
        items=[AgentApprovalResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/approvals/mine/{approval_id}",
    response_model=AgentApprovalResponse,
    summary="Get one of my Agent approvals",
)
async def get_my_approval(
    approval_id: Annotated[str, Path(min_length=1, max_length=64)],
    session: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
) -> AgentApprovalResponse:
    """查询当前用户的一笔审批详情."""
    service = AgentApprovalService(session, user, settings=get_settings())
    record = await service.get_for_requester(
        requester_id=user.id,
        approval_id=approval_id,
    )
    return AgentApprovalResponse.model_validate(record)


@router.get(
    "/runs/{trace_id}",
    response_model=TraceRunResponse,
    summary="Get an Agent trace run",
)
async def get_trace_run(
    trace_id: Annotated[str, Path(min_length=1, max_length=128)],
    _debugger: CurrentDebugger,
) -> TraceRunResponse:
    """返回脱敏 Trace; 只允许管理员或调试人员访问."""
    events = get_trace_buffer().get(trace_id)
    if not events:
        raise ResourceNotFoundException(
            message="Agent trace was not found",
            code="AGENT_TRACE_NOT_FOUND",
        )
    return TraceRunResponse(
        trace_id=trace_id,
        events=[TraceEventResponse.model_validate(event) for event in events],
    )


@router.post(
    "/actions/{confirmation_id}/confirm",
    response_model=ConfirmActionResponse,
    summary="Confirm a prepared Agent action",
)
async def confirm_action(
    confirmation_id: Annotated[str, Path(min_length=1, max_length=128)],
    request: ConfirmActionRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
) -> ConfirmActionResponse:
    """确认执行已 Prepare 的用户动作, nonce 与会话必须匹配."""
    service = ConfirmationService(
        session=session,
        user=user,
        settings=get_settings(),
    )
    result = await service.confirm(
        confirmation_id=confirmation_id,
        conversation_id=request.conversation_id,
        nonce=request.nonce,
    )
    return ConfirmActionResponse(
        success=True,
        action_type=result.operation,
        resource_no=result.resource_no,
        status=result.status,
        message=result.message,
        after_sales_no=result.after_sales_no,
    )
