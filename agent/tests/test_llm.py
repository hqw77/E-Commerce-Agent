"""Tests for the TASK-006.1 DeepSeek LLM provider."""

import asyncio
import json

import httpx
import pytest
from app.core.config import Settings
from langchain_core.language_models.fake_chat_models import (
    FakeListChatModel,
    FakeMessagesListChatModel,
)
from langchain_core.messages import AIMessage
from langchain_openai import ChatOpenAI

from agent.exceptions import (
    AgentLLMConfigurationError,
    AgentLLMResponseError,
    AgentLLMTimeoutError,
    AgentLLMUnavailableError,
)
from agent.llm import ConversationMessage, DeepSeekLLMProvider


def make_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "deepseek_api_key": "test-api-key",
        "deepseek_base_url": "https://api.deepseek.com",
        "deepseek_model": "deepseek-chat",
    }
    values.update(overrides)
    return Settings(**values)


def test_provider_rejects_missing_api_key() -> None:
    with pytest.raises(AgentLLMConfigurationError) as exc_info:
        DeepSeekLLMProvider(make_settings(deepseek_api_key=""))

    assert exc_info.value.code == "AGENT_LLM_NOT_CONFIGURED"
    assert "test-api-key" not in str(exc_info.value)


def test_provider_reuses_existing_deepseek_settings() -> None:
    provider = DeepSeekLLMProvider(make_settings())

    assert isinstance(provider._model, ChatOpenAI)
    assert provider.model_name == "deepseek-chat"
    assert provider.base_url == "https://api.deepseek.com"
    assert provider._model.model_name == "deepseek-chat"
    assert provider._model.openai_api_base == "https://api.deepseek.com"
    assert provider._model.extra_body == {"max_tokens": 1024}


@pytest.mark.asyncio
async def test_generate_with_injected_model() -> None:
    provider = DeepSeekLLMProvider(
        make_settings(),
        chat_model=FakeListChatModel(responses=["hello from fake"]),
    )

    result = await provider.generate(
        system_prompt="system",
        messages=[ConversationMessage(role="user", content="earlier")],
        user_message="current",
    )

    assert result.text == "hello from fake"
    assert result.input_tokens == 0
    assert result.output_tokens == 0
    assert result.total_tokens == 0


@pytest.mark.asyncio
async def test_generate_reads_usage_metadata() -> None:
    provider = DeepSeekLLMProvider(
        make_settings(),
        chat_model=FakeMessagesListChatModel(
            responses=[
                AIMessage(
                    content="answer",
                    usage_metadata={
                        "input_tokens": 11,
                        "output_tokens": 7,
                        "total_tokens": 18,
                    },
                )
            ]
        ),
    )

    result = await provider.generate(
        system_prompt="system",
        user_message="question",
    )

    assert result.text == "answer"
    assert result.input_tokens == 11
    assert result.output_tokens == 7
    assert result.total_tokens == 18


@pytest.mark.asyncio
async def test_generate_rejects_empty_model_response() -> None:
    provider = DeepSeekLLMProvider(
        make_settings(),
        chat_model=FakeListChatModel(responses=[""]),
    )

    with pytest.raises(AgentLLMResponseError):
        await provider.generate(system_prompt="system", user_message="question")


@pytest.mark.asyncio
async def test_generate_rejects_empty_user_message() -> None:
    provider = DeepSeekLLMProvider(
        make_settings(),
        chat_model=FakeListChatModel(responses=["unused"]),
    )

    with pytest.raises(AgentLLMConfigurationError):
        await provider.generate(system_prompt="system", user_message="  ")


@pytest.mark.asyncio
async def test_generate_maps_provider_failure() -> None:
    provider = DeepSeekLLMProvider(
        make_settings(),
        chat_model=FakeListChatModel(responses=[]),
    )

    with pytest.raises(AgentLLMUnavailableError):
        await provider.generate(system_prompt="system", user_message="question")


@pytest.mark.asyncio
async def test_generate_maps_timeout() -> None:
    class SlowModel(FakeListChatModel):
        async def ainvoke(self, *args: object, **kwargs: object) -> object:
            await asyncio.sleep(2)
            return AIMessage(content="too late")

    provider = DeepSeekLLMProvider(
        make_settings(agent_llm_timeout_seconds=1),
        chat_model=SlowModel(responses=["unused"]),
    )

    with pytest.raises(AgentLLMTimeoutError):
        await provider.generate(system_prompt="system", user_message="question")


def test_provider_does_not_expose_api_key_in_repr() -> None:
    provider = DeepSeekLLMProvider(make_settings())

    assert "test-api-key" not in repr(provider)
    assert "test-api-key" not in str(provider._model)


@pytest.mark.asyncio
async def test_provider_sends_deepseek_max_tokens_not_max_completion_tokens() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "created": 1,
                "model": "deepseek-chat",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": "wire-ok",
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 1,
                    "completion_tokens": 1,
                    "total_tokens": 2,
                },
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
    ) as client:
        chat_model = ChatOpenAI(
            model="deepseek-chat",
            api_key="test-api-key",
            base_url="https://api.deepseek.com",
            http_async_client=client,
            http_socket_options=(),
            extra_body={"max_tokens": 1024},
        )
        provider = DeepSeekLLMProvider(make_settings(), chat_model=chat_model)

        result = await provider.generate(
            system_prompt="system",
            user_message="question",
            max_output_tokens=64,
        )

    body = captured["body"]
    assert isinstance(body, dict)
    assert body["max_tokens"] == 64
    assert "max_completion_tokens" not in body
    assert result.text == "wire-ok"
    assert result.total_tokens == 2
