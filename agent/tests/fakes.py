"""Shared fakes for TASK-006 tests; no external LLM or RAG calls."""

from __future__ import annotations

from collections.abc import Sequence
from types import SimpleNamespace

from app.core.config import Settings
from app.schemas.knowledge import RetrievalItem

from agent.llm import ConversationMessage, LLMResult, ToolAwareResult, ToolCall


class FakeLLM:
    def __init__(
        self,
        responses: Sequence[str],
        *,
        tool_calls: Sequence[ToolCall] | None = None,
    ) -> None:
        self.responses = list(responses)
        self.tool_calls = list(tool_calls or [])
        self.calls: list[dict[str, object]] = []
        self.tool_planning_calls: list[dict[str, object]] = []

    async def generate(
        self,
        *,
        system_prompt: str,
        messages: Sequence[ConversationMessage] = (),
        user_message: str,
        max_output_tokens: int | None = None,
    ) -> LLMResult:
        self.calls.append(
            {
                "system_prompt": system_prompt,
                "messages": list(messages),
                "user_message": user_message,
                "max_output_tokens": max_output_tokens,
            }
        )
        if not self.responses:
            raise RuntimeError("fake response queue exhausted")
        return LLMResult(
            text=self.responses.pop(0),
            input_tokens=3,
            output_tokens=2,
            total_tokens=5,
        )

    async def generate_with_tools(
        self,
        *,
        system_prompt: str,
        messages: Sequence[ConversationMessage] = (),
        user_message: str,
        tools: Sequence[dict[str, object]],
        max_output_tokens: int | None = None,
    ) -> ToolAwareResult:
        self.tool_planning_calls.append(
            {
                "system_prompt": system_prompt,
                "messages": list(messages),
                "user_message": user_message,
                "tools": list(tools),
                "max_output_tokens": max_output_tokens,
            }
        )
        calls = self.tool_calls
        self.tool_calls = []
        return ToolAwareResult(
            text=self.responses.pop(0) if self.responses else "",
            tool_calls=calls,
            input_tokens=4,
            output_tokens=2,
            total_tokens=6,
        )


class FakeRetrieval:
    def __init__(self, items: Sequence[RetrievalItem] | None = None) -> None:
        self.items = list(items or [])
        self.fail = False

    async def retrieve(self, **kwargs: object) -> list[RetrievalItem]:
        if self.fail:
            from app.core.exceptions import AppException

            raise AppException(
                message="forced retrieval failure",
                code="RAG_RETRIEVAL_UNAVAILABLE",
                status_code=503,
            )
        return list(self.items)


def make_item(
    *,
    chunk_id: int = 1,
    document_id: int = 10,
    version_id: int = 20,
    content: str = "退款需要经过审核。",
    score: float = 0.9,
) -> RetrievalItem:
    return RetrievalItem(
        chunk_id=chunk_id,
        document_id=document_id,
        version_id=version_id,
        document_title="售后规则",
        content=content,
        score=score,
        page_number=None,
        section_title="退款",
        original_filename="rules.md",
    )


def make_user(
    user_id: int,
    *,
    is_admin: bool = False,
    is_debugger: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=user_id,
        email=f"agent-{user_id}@example.com",
        is_active=True,
        is_admin=is_admin,
        is_debugger=is_debugger,
    )


def make_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "deepseek_api_key": "test-api-key",
        "agent_rate_limit_per_minute": 1000,
    }
    values.update(overrides)
    return Settings(**values)
