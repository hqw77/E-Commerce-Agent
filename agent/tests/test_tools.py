"""Tool registry, schema, and executor safety tests."""

from __future__ import annotations

from uuid import uuid4

import pytest
from app.core.config import Settings

from agent.tests.fakes import make_user
from agent.tools.context import ToolContext
from agent.tools.errors import (
    AgentToolArgumentError,
    AgentToolLimitError,
    AgentToolNotFoundError,
    ToolResult,
)
from agent.tools.executor import ToolExecutor
from agent.tools.registry import RegisteredTool, ToolRegistry
from agent.tools.schemas import SearchProductsInput


class DummyContextTool:
    pass


def make_context() -> ToolContext:
    settings = Settings(_env_file=None)
    return ToolContext(
        user=make_user(uuid4().int),  # type: ignore[arg-type]
        session=None,  # type: ignore[arg-type]
        settings=settings,
        conversation_id=uuid4(),
        confirmation_store=None,  # type: ignore[arg-type]
    )


async def echo_handler(context: ToolContext, args: object) -> ToolResult:
    return ToolResult(ok=True, tool="echo", data={"ok": True})


def test_registry_is_a_strict_whitelist() -> None:
    registry = ToolRegistry()
    registry.register(
        RegisteredTool(
            name="echo",
            description="echo",
            args_schema=SearchProductsInput,
            kind="READ",
            handler=echo_handler,
        )
    )

    assert registry.names() == frozenset({"echo"})
    assert registry.get("echo").name == "echo"
    with pytest.raises(AgentToolNotFoundError):
        registry.get("missing")
    with pytest.raises(ValueError):
        registry.register(
            RegisteredTool(
                name="echo",
                description="duplicate",
                args_schema=SearchProductsInput,
                kind="READ",
                handler=echo_handler,
            )
        )


def test_tool_schema_forbids_identity_and_extra_fields() -> None:
    with pytest.raises(ValueError):
        SearchProductsInput.model_validate(
            {"query": "shoe", "user_id": 123}
        )


@pytest.mark.asyncio
async def test_executor_validates_args_and_enforces_limit() -> None:
    registry = ToolRegistry()
    registry.register(
        RegisteredTool(
            name="echo",
            description="echo",
            args_schema=SearchProductsInput,
            kind="READ",
            handler=echo_handler,
        )
    )
    executor = ToolExecutor(registry, max_calls=1)
    context = make_context()

    result = await executor.execute(
        "echo",
        {"query": "shoe"},
        context,
    )
    assert result.ok

    with pytest.raises(AgentToolLimitError):
        await executor.execute("echo", {"query": "shoe"}, context)


@pytest.mark.asyncio
async def test_executor_rejects_invalid_arguments() -> None:
    registry = ToolRegistry()
    registry.register(
        RegisteredTool(
            name="echo",
            description="echo",
            args_schema=SearchProductsInput,
            kind="READ",
            handler=echo_handler,
        )
    )
    executor = ToolExecutor(registry, max_calls=4)
    with pytest.raises(AgentToolArgumentError):
        await executor.execute("echo", {"query": ""}, make_context())
