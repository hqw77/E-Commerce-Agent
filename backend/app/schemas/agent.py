"""Agent API request and response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ChatRequest(BaseModel):
    """Authenticated chat request; identity is never accepted from the body."""

    model_config = ConfigDict(extra="forbid")

    conversation_id: UUID | None = None
    message: str = Field(min_length=1, max_length=4000)

    @field_validator("message")
    @classmethod
    def normalize_message(cls, value: str) -> str:
        """去除消息首尾空白并拒绝空消息."""
        value = value.strip()
        if not value:
            raise ValueError("Message must not be empty")
        return value


class SourceResponse(BaseModel):
    """RAG 来源响应."""
    document_id: int
    version_id: int
    chunk_id: int
    title: str
    section_title: str | None
    page_number: int | None


class ChatResponse(BaseModel):
    """Agent 聊天响应."""
    conversation_id: UUID
    message_id: UUID
    answer: str
    sources: list[SourceResponse]
    pending_action: PendingActionResponse | None = None
    created_at: datetime
    trace_id: str | None = None


class TraceEventResponse(BaseModel):
    """Trace 单事件响应."""
    trace_id: str
    request_id: str
    conversation_id: str
    user_id: int
    node_name: str | None
    event_type: str
    intent: str | None
    route: str | None
    tool_name: str | None
    arguments_summary: dict[str, Any] | None
    risk_level: str | None
    execution_status: str
    duration_ms: float | None
    result_summary: dict[str, Any] | None
    error_code: str | None
    timestamp: str


class TraceRunResponse(BaseModel):
    """一次 Trace 的全部事件."""
    trace_id: str
    events: list[TraceEventResponse]


class PendingActionResponse(BaseModel):
    """PREPARE 动作的待确认信息."""
    confirmation_id: str
    nonce: str
    conversation_id: UUID
    action_type: str
    title: str
    resource_no: str
    effect: str
    summary: str
    expires_at: datetime
    approval_required: bool = False
    approval_id: str | None = None
    approval_status: str | None = None


class ConfirmActionRequest(BaseModel):
    """用户确认动作参数."""
    model_config = ConfigDict(extra="forbid")

    conversation_id: UUID
    nonce: str = Field(min_length=1, max_length=256)


class ConfirmActionResponse(BaseModel):
    """确认执行结果."""
    success: bool
    action_type: str
    resource_no: str
    status: str
    message: str
    after_sales_no: str | None = None
