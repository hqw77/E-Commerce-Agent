"""Request-level Agent runtime: rate limit, lock, timeout, graph invocation."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from app.core.config import Settings, get_settings
from app.core.exceptions import AppException
from app.models.user import User
from app.services.rag.retrieval_service import KnowledgeRetrievalService
from app.services.rag.runtime import get_embedding_provider, get_vector_store
from sqlalchemy.ext.asyncio import AsyncSession

from agent.context import AgentRuntimeContext
from agent.conversation import ConversationStore, new_conversation_id
from agent.exceptions import (
    AgentConversationBusyError,
    AgentDisabledError,
    AgentExecutionTimeoutError,
    AgentInternalError,
)
from agent.graph import COMPILED_AGENT_GRAPH
from agent.guardrails import validate_user_message
from agent.llm import AgentLLM, DeepSeekLLMProvider
from agent.rate_limit import RedisRateLimiter
from agent.state import SourceRef
from agent.tools import TOOL_REGISTRY
from agent.tools.confirmation import ConfirmationStore
from agent.tools.executor import ToolExecutor
from agent.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

_agent_llm: AgentLLM | None = None


def get_agent_llm(settings: Settings | None = None) -> AgentLLM:
    """Return the process-level provider without creating a key-bearing log."""
    global _agent_llm
    if _agent_llm is None:
        _agent_llm = DeepSeekLLMProvider(settings or get_settings())
    return _agent_llm


@dataclass(frozen=True, slots=True)
class ChatResult:
    conversation_id: UUID
    message_id: UUID
    answer: str
    sources: list[SourceRef]
    created_at: datetime
    pending_action: dict[str, Any] | None = None


class AgentRuntime:
    """Owns one request's trusted context and serializes each conversation."""

    def __init__(
        self,
        session: AsyncSession,
        user: User,
        settings: Settings | None = None,
        *,
        llm: AgentLLM | None = None,
        retrieval: KnowledgeRetrievalService | None = None,
        conversation_store: ConversationStore | None = None,
        rate_limiter: RedisRateLimiter | None = None,
        graph: Any | None = None,
        tool_registry: ToolRegistry | None = None,
        tool_executor: ToolExecutor | None = None,
        confirmation_store: ConfirmationStore | None = None,
    ) -> None:
        self.session = session
        self.user = user
        self.settings = settings or get_settings()
        self.llm = llm or get_agent_llm(self.settings)
        self.retrieval = retrieval or KnowledgeRetrievalService(
            session,
            self.settings,
            embedding=get_embedding_provider(self.settings),
            vector_store=get_vector_store(self.settings),
        )
        self.conversation_store = conversation_store or ConversationStore(
            self.settings
        )
        self.rate_limiter = rate_limiter or RedisRateLimiter(self.settings)
        self.graph = graph or COMPILED_AGENT_GRAPH
        self.tool_registry = tool_registry or TOOL_REGISTRY
        self.confirmation_store = confirmation_store or ConfirmationStore(
            self.settings
        )
        self.tool_executor = tool_executor or ToolExecutor(
            self.tool_registry,
            max_calls=self.settings.agent_max_tool_calls_per_turn,
        )

    async def chat(
        self,
        *,
        message: str,
        conversation_id: UUID | None = None,
    ) -> ChatResult:
        if not self.settings.agent_enabled:
            raise AgentDisabledError()

        normalized = validate_user_message(message, self.settings)
        await self.rate_limiter.check(self.user.id)

        new_conversation = conversation_id is None
        active_conversation_id = conversation_id or new_conversation_id()
        lock_token = uuid4().hex
        if not await self.conversation_store.acquire_lock(
            user_id=self.user.id,
            conversation_id=active_conversation_id,
            token=lock_token,
        ):
            raise AgentConversationBusyError()

        request_id = uuid4().hex
        started_at = datetime.now(UTC)
        context = AgentRuntimeContext(
            request_id=request_id,
            user=self.user,
            session=self.session,
            settings=self.settings,
            llm=self.llm,
            retrieval=self.retrieval,
            conversation_store=self.conversation_store,
            lock_token=lock_token,
            is_new_conversation=new_conversation,
            tool_executor=self.tool_executor,
            confirmation_store=self.confirmation_store,
        )
        initial_state = {
            "request_id": request_id,
            "conversation_id": str(active_conversation_id),
            "user_id": self.user.id,
            "user_message": normalized,
            "started_at": started_at,
        }

        try:
            async with asyncio.timeout(
                self.settings.agent_max_execution_seconds
            ):
                final_state = await self.graph.ainvoke(
                    initial_state,
                    context=context,
                )
        except TimeoutError as exc:
            raise AgentExecutionTimeoutError() from exc
        except AgentInternalError:
            raise
        except Exception as exc:
            if isinstance(exc, AppException):
                raise
            logger.error(
                "agent_execution_failed",
                extra={
                    "request_id": request_id,
                    "error_type": type(exc).__name__,
                },
            )
            raise AgentInternalError() from exc
        finally:
            await self.conversation_store.release_lock(
                user_id=self.user.id,
                conversation_id=active_conversation_id,
                token=lock_token,
            )

        return ChatResult(
            conversation_id=active_conversation_id,
            message_id=uuid4(),
            answer=str(final_state["answer"]),
            sources=list(final_state.get("sources", [])),
            created_at=datetime.now(UTC),
            pending_action=final_state.get("pending_action"),
        )
