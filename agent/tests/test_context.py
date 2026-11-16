"""Context budget boundary tests for TASK-006."""

from __future__ import annotations

import pytest

from agent.exceptions import (
    AgentContextBudgetExceededError,
    AgentOutputRejectedError,
)
from agent.guardrails import select_context, sources_from_items, validate_output
from agent.state import HistoryMessage, SourceRef
from agent.tests.fakes import make_item, make_settings


def pair(user: str, assistant: str) -> list[HistoryMessage]:
    return [
        HistoryMessage(role="user", content=user),
        HistoryMessage(role="assistant", content=assistant),
    ]


def test_history_budget_includes_current_message_and_latest_turn() -> None:
    history = [
        *pair("old-user", "old-assistant"),
        *pair("latest-user", "latest-assistant"),
    ]
    current = "current"
    latest_length = len("latest-user") + len("latest-assistant")
    settings = make_settings(
        agent_max_history_chars=len(current) + latest_length,
        agent_max_context_chars=10000,
    )

    selection = select_context(
        history=history,
        user_message=current,
        rag_items=[],
        settings=settings,
    )

    assert selection.history == history[2:]
    assert selection.rag_items == []


def test_history_budget_over_by_one_raises() -> None:
    history = pair("user", "assistant")
    current = "current"
    latest_length = len("user") + len("assistant")
    settings = make_settings(
        agent_max_history_chars=len(current) + latest_length - 1,
        agent_max_context_chars=10000,
    )

    with pytest.raises(AgentContextBudgetExceededError):
        select_context(
            history=history,
            user_message=current,
            rag_items=[],
            settings=settings,
        )


def test_rag_budget_only_counts_selected_complete_chunks() -> None:
    first = make_item(chunk_id=1, content="a" * 6, score=0.95)
    second = make_item(chunk_id=2, content="b" * 6, score=0.90)
    settings = make_settings(
        agent_max_history_chars=100,
        agent_max_rag_context_chars=9,
        agent_max_context_chars=100,
    )

    selection = select_context(
        history=[],
        user_message="q",
        rag_items=[first, second],
        settings=settings,
    )

    assert [item.chunk_id for item in selection.rag_items] == [1]
    assert '"chunk_id":1' in selection.context_text
    assert "trust" in selection.context_text


def test_total_context_budget_stops_adding_older_turns() -> None:
    history = [
        *pair("old-user", "old-assistant"),
        *pair("new-user", "new-assistant"),
    ]
    settings = make_settings(
        agent_max_history_chars=10000,
        agent_max_context_chars=(
            len("current")
            + len("new-user")
            + len("new-assistant")
        ),
    )

    selection = select_context(
        history=history,
        user_message="current",
        rag_items=[],
        settings=settings,
    )

    assert selection.history == history[2:]


def test_rag_cannot_exceed_total_context_budget() -> None:
    history = pair("user", "assistant")
    item = make_item(content="x" * 20)
    settings = make_settings(
        agent_max_history_chars=100,
        agent_max_rag_context_chars=100,
        agent_max_context_chars=(
            len("current") + len("user") + len("assistant") + 10
        ),
    )

    selection = select_context(
        history=history,
        user_message="current",
        rag_items=[item],
        settings=settings,
    )

    assert selection.rag_items == []


def test_sources_are_built_from_retrieval_items() -> None:
    items = [make_item(chunk_id=7, document_id=8, version_id=9)]
    sources = sources_from_items(items)

    assert len(sources) == 1
    assert sources[0].chunk_id == 7
    assert sources[0].document_id == 8
    assert sources[0].version_id == 9


def test_output_rejects_source_not_in_retrieved_items() -> None:
    settings = make_settings()
    item = make_item(chunk_id=1)

    with pytest.raises(AgentOutputRejectedError):
        validate_output(
            "answer",
            sources=[
                SourceRef(
                    document_id=99,
                    version_id=99,
                    chunk_id=99,
                    title="forged",
                    section_title=None,
                    page_number=None,
                )
            ],
            retrieved_items=[item],
            settings=settings,
        )
