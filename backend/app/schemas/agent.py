"""Agent API request and response schemas."""

from __future__ import annotations

from datetime import datetime
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
        value = value.strip()
        if not value:
            raise ValueError("Message must not be empty")
        return value


class SourceResponse(BaseModel):
    document_id: int
    version_id: int
    chunk_id: int
    title: str
    section_title: str | None
    page_number: int | None


class ChatResponse(BaseModel):
    conversation_id: UUID
    message_id: UUID
    answer: str
    sources: list[SourceResponse]
    pending_action: PendingActionResponse | None = None
    created_at: datetime


class PendingActionResponse(BaseModel):
    confirmation_id: str
    nonce: str
    conversation_id: UUID
    action_type: str
    title: str
    resource_no: str
    effect: str
    summary: str
    expires_at: datetime


class ConfirmActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversation_id: UUID
    nonce: str = Field(min_length=1, max_length=256)


class ConfirmActionResponse(BaseModel):
    success: bool
    action_type: str
    resource_no: str
    status: str
    message: str
    after_sales_no: str | None = None
