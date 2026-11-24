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
from app.api.dependencies import CurrentUser
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
    """接收用户消息并执行一次 Agent 请求. 用户身份由 CurrentUser 提供."""
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
    "/runs/{trace_id}",
    response_model=TraceRunResponse,
    summary="Get an Agent trace run",
)
async def get_trace_run(
    trace_id: Annotated[str, Path(min_length=1, max_length=128)],
    user: CurrentUser,
) -> TraceRunResponse:
    """Return a redacted trace to its owner or an administrator.

    The trace buffer is process-local and intentionally not a durable audit
    store. Production log output remains the source of record.
    """
    events = get_trace_buffer().get(trace_id)
    if not events:
        raise ResourceNotFoundException(
            message="Agent trace was not found",
            code="AGENT_TRACE_NOT_FOUND",
        )
    # 普通用户只能看自己的 trace; 对其他用户的 trace 返回 404 而不是 403,
    # 避免通过错误码推断某个 trace 是否存在.
    if not user.is_admin and any(
        int(event.get("user_id", -1)) != user.id for event in events
    ):
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
    """确认执行一个已 Prepare 的动作. nonce 和会话 ID 必须与 Redis 中记录匹配."""
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
