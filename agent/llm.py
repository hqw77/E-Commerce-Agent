"""DeepSeek LLM provider built on LangChain's ChatOpenAI adapter."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

from app.core.config import Settings, get_settings
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from agent.exceptions import (
    AgentLLMConfigurationError,
    AgentLLMResponseError,
    AgentLLMTimeoutError,
    AgentLLMUnavailableError,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ConversationMessage:
    """A model-visible history message; identity is never stored here."""

    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True, slots=True)
class LLMResult:
    """Normalized text and token usage returned by the provider."""

    text: str
    input_tokens: int
    output_tokens: int
    total_tokens: int


@dataclass(frozen=True, slots=True)
class ToolCall:
    """One tool invocation requested by the model."""

    name: str
    args: dict[str, Any]
    id: str | None = None


@dataclass(frozen=True, slots=True)
class ToolAwareResult:
    """Model text plus any tool calls, with normalized token usage."""

    text: str
    tool_calls: list[ToolCall]
    input_tokens: int
    output_tokens: int
    total_tokens: int


def _as_int(value: Any) -> int:
    try:
        return max(int(value), 0)
    except (TypeError, ValueError):
        return 0


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)

    return str(content) if content is not None else ""


class DeepSeekLLMProvider:
    """Async DeepSeek chat model adapter.

    The provider owns configuration validation and model initialization.
    A test model can be injected without an API key or network access.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        chat_model: BaseChatModel | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._model = chat_model or self._build_model()
        self._timeout_seconds = float(self.settings.agent_llm_timeout_seconds)

    @property
    def model_name(self) -> str:
        return self.settings.deepseek_model

    @property
    def base_url(self) -> str:
        return self.settings.deepseek_base_url

    def _build_model(self) -> BaseChatModel:
        api_key = self.settings.deepseek_api_key.get_secret_value()
        if not api_key:
            raise AgentLLMConfigurationError()

        return ChatOpenAI(
            model=self.settings.deepseek_model,
            api_key=self.settings.deepseek_api_key,
            base_url=self.settings.deepseek_base_url,
            timeout=self.settings.agent_llm_timeout_seconds,
            max_retries=self.settings.agent_llm_max_retries,
            temperature=self.settings.agent_temperature,
            # langchain-openai 1.8.0 rewrites max_tokens to
            # max_completion_tokens; DeepSeek accepts max_tokens instead.
            extra_body={"max_tokens": self.settings.agent_max_output_tokens},
        )

    async def generate(
        self,
        *,
        system_prompt: str,
        messages: Sequence[ConversationMessage] = (),
        user_message: str,
        max_output_tokens: int | None = None,
    ) -> LLMResult:
        """Invoke DeepSeek and normalize the response and usage metadata."""
        if not system_prompt.strip():
            raise AgentLLMConfigurationError("System prompt must not be empty")
        if not user_message.strip():
            raise AgentLLMConfigurationError("User message must not be empty")

        output_limit = (
            max_output_tokens
            if max_output_tokens is not None
            else self.settings.agent_max_output_tokens
        )
        if output_limit < 1:
            raise AgentLLMConfigurationError(
                "max_output_tokens must be greater than zero"
            )

        langchain_messages: list[Any] = [SystemMessage(content=system_prompt)]
        for message in messages:
            if message.role == "user":
                langchain_messages.append(HumanMessage(content=message.content))
            elif message.role == "assistant":
                langchain_messages.append(AIMessage(content=message.content))
            else:
                raise AgentLLMConfigurationError(
                    f"Unsupported conversation role: {message.role}"
                )
        langchain_messages.append(HumanMessage(content=user_message))

        # Bind through extra_body so the wire parameter remains max_tokens;
        # binding max_tokens directly is rewritten by langchain-openai.
        model = self._model.bind(
            extra_body={"max_tokens": output_limit},
        )
        started = time.perf_counter()

        try:
            response = await asyncio.wait_for(
                model.ainvoke(langchain_messages),
                timeout=self._timeout_seconds,
            )
        except TimeoutError as exc:
            logger.warning(
                "agent_llm_timeout",
                extra={"model": self.model_name},
            )
            raise AgentLLMTimeoutError() from exc
        except Exception as exc:
            logger.warning(
                "agent_llm_unavailable",
                extra={"model": self.model_name, "error_type": type(exc).__name__},
            )
            raise AgentLLMUnavailableError() from exc

        text = _content_text(getattr(response, "content", "")).strip()
        if not text:
            raise AgentLLMResponseError()

        usage = getattr(response, "usage_metadata", None) or {}
        response_metadata = getattr(response, "response_metadata", None) or {}
        token_usage = response_metadata.get("token_usage") or {}

        input_tokens = _as_int(
            usage.get("input_tokens", token_usage.get("prompt_tokens"))
        )
        output_tokens = _as_int(
            usage.get("output_tokens", token_usage.get("completion_tokens"))
        )
        total_tokens = _as_int(
            usage.get(
                "total_tokens",
                token_usage.get(
                    "total_tokens",
                    input_tokens + output_tokens,
                ),
            )
        )
        if total_tokens == 0:
            total_tokens = input_tokens + output_tokens

        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.info(
            "agent_llm_completed",
            extra={
                "model": self.model_name,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
                "elapsed_ms": elapsed_ms,
            },
        )

        return LLMResult(
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
        )

    async def generate_with_tools(
        self,
        *,
        system_prompt: str,
        messages: Sequence[ConversationMessage] = (),
        user_message: str,
        tools: Sequence[dict[str, Any]],
        max_output_tokens: int | None = None,
    ) -> ToolAwareResult:
        """Invoke the model with only the caller-provided tool schemas."""
        if not system_prompt.strip():
            raise AgentLLMConfigurationError("System prompt must not be empty")
        if not user_message.strip():
            raise AgentLLMConfigurationError("User message must not be empty")

        output_limit = (
            max_output_tokens
            if max_output_tokens is not None
            else self.settings.agent_max_output_tokens
        )
        langchain_messages: list[Any] = [SystemMessage(content=system_prompt)]
        for message in messages:
            if message.role == "user":
                langchain_messages.append(HumanMessage(content=message.content))
            else:
                langchain_messages.append(AIMessage(content=message.content))
        langchain_messages.append(HumanMessage(content=user_message))

        model = self._model.bind_tools(list(tools)).bind(
            extra_body={"max_tokens": output_limit},
        )
        try:
            response = await asyncio.wait_for(
                model.ainvoke(langchain_messages),
                timeout=self._timeout_seconds,
            )
        except TimeoutError as exc:
            raise AgentLLMTimeoutError() from exc
        except Exception as exc:
            logger.warning(
                "agent_llm_tool_call_unavailable",
                extra={"model": self.model_name, "error_type": type(exc).__name__},
            )
            raise AgentLLMUnavailableError() from exc

        raw_calls = getattr(response, "tool_calls", None) or []
        parsed_calls: list[ToolCall] = []
        for raw in raw_calls:
            if not isinstance(raw, dict):
                continue
            args = raw.get("args")
            parsed_calls.append(
                ToolCall(
                    name=str(raw.get("name", "")),
                    args=args if isinstance(args, dict) else {},
                    id=str(raw["id"]) if raw.get("id") else None,
                )
            )

        text = _content_text(getattr(response, "content", "")).strip()
        if not text and not parsed_calls:
            raise AgentLLMResponseError()

        usage = getattr(response, "usage_metadata", None) or {}
        response_metadata = getattr(response, "response_metadata", None) or {}
        token_usage = response_metadata.get("token_usage") or {}
        input_tokens = _as_int(
            usage.get("input_tokens", token_usage.get("prompt_tokens"))
        )
        output_tokens = _as_int(
            usage.get("output_tokens", token_usage.get("completion_tokens"))
        )
        total_tokens = _as_int(
            usage.get(
                "total_tokens",
                token_usage.get("total_tokens", input_tokens + output_tokens),
            )
        )
        if total_tokens == 0:
            total_tokens = input_tokens + output_tokens

        return ToolAwareResult(
            text=text,
            tool_calls=parsed_calls,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
        )


# Design-facing alias; the concrete adapter is DeepSeek-specific.
AgentLLM = DeepSeekLLMProvider
