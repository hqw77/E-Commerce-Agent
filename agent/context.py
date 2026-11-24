"""Per-request LangGraph runtime context for TASK-006."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings
from app.models.user import User
from app.services.rag.retrieval_service import KnowledgeRetrievalService
from sqlalchemy.ext.asyncio import AsyncSession

from agent.conversation import ConversationStore
from agent.llm import AgentLLM
from agent.observability.trace import TraceRecorder
from agent.tools.confirmation import ConfirmationStore
from agent.tools.executor import ToolExecutor


@dataclass(slots=True)
class AgentRuntimeContext:
    """Trusted per-request dependencies, injected through graph context.

    This object is deliberately outside AgentState. It contains the ORM User,
    AsyncSession, request-specific RAG service and conversation lock token.
    """

    request_id: str
    user: User
    session: AsyncSession
    settings: Settings
    llm: AgentLLM
    retrieval: KnowledgeRetrievalService
    conversation_store: ConversationStore
    lock_token: str
    is_new_conversation: bool
    tool_executor: ToolExecutor | None = None
    confirmation_store: ConfirmationStore | None = None
    trace_id: str | None = None
    trace: TraceRecorder | None = None
