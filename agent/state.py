"""Serializable state and value objects for the TASK-006 Agent graph."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, TypedDict

from app.schemas.knowledge import RetrievalItem

AgentIntent = Literal[
    "GENERAL",
    "KNOWLEDGE",
    "TOOL",
    "UNSUPPORTED_ACTION",
]


@dataclass(frozen=True, slots=True)
class HistoryMessage:
    """A user or assistant message that may be sent back to the model."""

    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True, slots=True)
class TokenUsage:
    """Token usage for one or more LLM calls in this request."""

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0

    def plus(self, other: TokenUsage) -> TokenUsage:
        return TokenUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
        )


@dataclass(frozen=True, slots=True)
class SourceRef:
    """A source reference built only by the backend from RetrievalItem."""

    document_id: int
    version_id: int
    chunk_id: int
    title: str
    section_title: str | None
    page_number: int | None


class AgentState(TypedDict, total=False):
    """The graph state. ORM User and AsyncSession must never enter this type."""

    request_id: str
    conversation_id: str
    conversation_created_at: str
    user_id: int
    user_message: str
    history: list[HistoryMessage]
    intent: AgentIntent
    retrieved_items: list[RetrievalItem]
    context_text: str
    tool_name: str | None
    tool_args: dict[str, object]
    tool_result: dict[str, object] | None
    tool_call_count: int
    pending_action: dict[str, object] | None
    answer: str
    sources: list[SourceRef]
    error_code: str | None
    token_usage: TokenUsage
    started_at: datetime
