"""Agent approval request/response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ApprovalStatus = Literal[
    "pending",
    "approved",
    "rejected",
    "executed",
    "failed",
    "expired",
]


class AgentApprovalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    approval_id: str
    operation: str
    resource_no: str
    status: ApprovalStatus
    arguments: dict[str, object]
    before_data: dict[str, object]
    planned_data: dict[str, object]
    action_hash: str
    requester_id: int
    approver_id: int | None
    conversation_id: str
    thread_id: str
    review_note: str | None
    error_code: str | None
    expires_at: datetime
    reviewed_at: datetime | None
    executed_at: datetime | None
    created_at: datetime


class AgentApprovalListResponse(BaseModel):
    items: list[AgentApprovalResponse]
    total: int
    page: int
    page_size: int


class AgentApprovalDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_note: str | None = Field(default=None, max_length=2000)
