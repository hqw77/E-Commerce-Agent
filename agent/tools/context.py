"""Per-request context passed to business tools."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.core.config import Settings
from app.models.user import User
from sqlalchemy.ext.asyncio import AsyncSession

from agent.observability.trace import TraceRecorder
from agent.tools.confirmation import ConfirmationStore


@dataclass(slots=True)
class ToolContext:
    """Trusted dependencies; the model never supplies these fields."""

    user: User
    session: AsyncSession
    settings: Settings
    conversation_id: UUID
    confirmation_store: ConfirmationStore
    trace: TraceRecorder | None = None
    route: str | None = None
