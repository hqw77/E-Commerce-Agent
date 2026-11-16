"""TASK-006/TASK-007 Agent chat and confirmation API."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path
from sqlalchemy.ext.asyncio import AsyncSession

from agent.runtime import AgentRuntime
from agent.tools.confirmation import ConfirmationService
from app.api.dependencies import CurrentUser
from app.core.config import get_settings
from app.db.session import get_db
from app.schemas.agent import (
    ChatRequest,
    ChatResponse,
    ConfirmActionRequest,
    ConfirmActionResponse,
    PendingActionResponse,
    SourceResponse,
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
