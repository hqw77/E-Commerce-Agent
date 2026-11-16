"""Deterministic input/output guardrails and dynamic context budgeting."""

from __future__ import annotations

import itertools
import json
import re
from dataclasses import dataclass

from app.core.config import Settings
from app.schemas.knowledge import RetrievalItem

from agent.exceptions import (
    AgentContextBudgetExceededError,
    AgentInputInvalidError,
    AgentOutputRejectedError,
)
from agent.state import HistoryMessage, SourceRef

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_INJECTION_PATTERNS = (
    "ignore previous",
    "ignore all previous",
    "system prompt",
    "developer mode",
    "忽略之前",
    "忽略以上",
    "输出系统提示",
    "系统提示词",
    "越狱",
)
_SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
)


@dataclass(frozen=True, slots=True)
class ContextSelection:
    """The bounded history and RAG data that may be sent to the model."""

    history: list[HistoryMessage]
    rag_items: list[RetrievalItem]
    context_text: str


def validate_user_message(message: str, settings: Settings) -> str:
    """Normalize and validate an untrusted user message."""
    normalized = _CONTROL_CHARS.sub("", message).strip()
    if not normalized:
        raise AgentInputInvalidError("Agent message must not be empty")
    if len(normalized) > settings.agent_max_input_chars:
        raise AgentInputInvalidError()
    return normalized


def looks_like_prompt_injection(message: str) -> bool:
    """Return a heuristic signal; it is not an authorization boundary."""
    lowered = message.casefold()
    return any(pattern in lowered for pattern in _INJECTION_PATTERNS)


def _complete_turns(
    history: list[HistoryMessage],
) -> list[tuple[HistoryMessage, HistoryMessage]]:
    turns: list[tuple[HistoryMessage, HistoryMessage]] = []
    for left, right in itertools.pairwise(history):
        if left.role == "user" and right.role == "assistant":
            turns.append((left, right))
    return turns


def _flat(turns: list[tuple[HistoryMessage, HistoryMessage]]) -> list[HistoryMessage]:
    return [message for turn in turns for message in turn]


def select_context(
    *,
    history: list[HistoryMessage],
    user_message: str,
    rag_items: list[RetrievalItem],
    settings: Settings,
) -> ContextSelection:
    """Select whole turns and whole RAG chunks under deterministic char budgets."""
    current_length = len(user_message)
    if current_length > settings.agent_max_history_chars:
        raise AgentContextBudgetExceededError()

    turns = _complete_turns(history)
    latest_turn = turns[-1] if turns else None
    latest_length = (
        len(latest_turn[0].content) + len(latest_turn[1].content)
        if latest_turn
        else 0
    )
    history_length = current_length + latest_length

    if history_length > settings.agent_max_history_chars:
        raise AgentContextBudgetExceededError()
    if history_length > settings.agent_max_context_chars:
        raise AgentContextBudgetExceededError()

    selected_turns: list[tuple[HistoryMessage, HistoryMessage]] = (
        [latest_turn] if latest_turn else []
    )
    older_turns = turns[:-1] if latest_turn else []
    for turn in reversed(older_turns):
        turn_length = len(turn[0].content) + len(turn[1].content)
        if history_length + turn_length > settings.agent_max_history_chars:
            break
        if history_length + turn_length > settings.agent_max_context_chars:
            break
        selected_turns.insert(0, turn)
        history_length += turn_length

    selected_rag: list[RetrievalItem] = []
    rag_length = 0
    for item in sorted(rag_items, key=lambda value: value.score, reverse=True):
        item_length = len(item.content)
        if rag_length + item_length > settings.agent_max_rag_context_chars:
            break
        if history_length + rag_length + item_length > settings.agent_max_context_chars:
            break
        selected_rag.append(item)
        rag_length += item_length

    context_payload = {
        "trust": "untrusted",
        "items": [
            {
                "chunk_id": item.chunk_id,
                "document_id": item.document_id,
                "version_id": item.version_id,
                "title": item.document_title,
                "section_title": item.section_title,
                "page_number": item.page_number,
                "content": item.content,
            }
            for item in selected_rag
        ],
    }
    context_text = json.dumps(
        context_payload,
        ensure_ascii=False,
        separators=(",", ":"),
    )

    return ContextSelection(
        history=_flat(selected_turns),
        rag_items=selected_rag,
        context_text=context_text,
    )


def sources_from_items(items: list[RetrievalItem]) -> list[SourceRef]:
    """Build source objects in the backend; the model never supplies sources."""
    return [
        SourceRef(
            document_id=item.document_id,
            version_id=item.version_id,
            chunk_id=item.chunk_id,
            title=item.document_title,
            section_title=item.section_title,
            page_number=item.page_number,
        )
        for item in items
    ]


def validate_output(
    answer: str,
    *,
    sources: list[SourceRef],
    retrieved_items: list[RetrievalItem],
    settings: Settings,
) -> str:
    """Apply deterministic checks; this is defense in depth, not an ACL."""
    normalized = answer.strip()
    if not normalized:
        raise AgentOutputRejectedError()
    if len(normalized) > settings.agent_max_output_chars:
        raise AgentOutputRejectedError("Agent output is too long")

    for pattern in _SECRET_PATTERNS:
        if pattern.search(normalized):
            raise AgentOutputRejectedError()

    allowed_chunk_ids = {item.chunk_id for item in retrieved_items}
    if any(source.chunk_id not in allowed_chunk_ids for source in sources):
        raise AgentOutputRejectedError("Agent source is not in retrieved context")

    return normalized
