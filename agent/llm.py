"""DeepSeek LLM Provider.

文件职责:
- 用 LangChain ChatOpenAI 适配 DeepSeek OpenAI 兼容接口.
- 统一普通对话和 Tool Calling 的返回结构.
- 处理超时, 供应商异常和 token 用量.
- 允许测试注入 fake chat model, 不访问网络.

核心边界:
Provider 只负责模型调用; 权限, 工具白名单和业务状态由 Graph/Executor 处理.
"""

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
    """模型可见的历史消息.

    Args:
        role: user 或 assistant.
        content: 消息文本; 不包含用户身份.
    """

    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True, slots=True)
class LLMResult:
    """普通模型调用的归一化结果.

    Args:
        text: 模型文本.
        input_tokens: 输入 token 数.
        output_tokens: 输出 token 数.
        total_tokens: 总 token 数.
    """

    text: str
    input_tokens: int
    output_tokens: int
    total_tokens: int


@dataclass(frozen=True, slots=True)
class ToolCall:
    """模型请求的一次工具调用.

    Args:
        name: 工具名.
        args: 模型生成的参数.
        id: 供应商返回的调用 ID.
    """

    name: str
    args: dict[str, Any]
    id: str | None = None


@dataclass(frozen=True, slots=True)
class ToolAwareResult:
    """带 Tool Calls 的模型结果.

    Args:
        text: 模型文本, 可能为空.
        tool_calls: 模型请求的工具调用.
        input_tokens: 输入 token 数.
        output_tokens: 输出 token 数.
        total_tokens: 总 token 数.
    """

    text: str
    tool_calls: list[ToolCall]
    input_tokens: int
    output_tokens: int
    total_tokens: int


def _as_int(value: Any) -> int:
    """把 token 用量安全转换为非负整数."""
    try:
        return max(int(value), 0)
    except (TypeError, ValueError):
        return 0


def _content_text(content: Any) -> str:
    """兼容字符串和 LangChain content block 列表两种返回格式."""
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
    """DeepSeek 异步聊天模型适配器.

    Provider 负责配置校验, 模型初始化和调用超时.
    测试可以注入 BaseChatModel, 不需要 API Key 或网络.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        chat_model: BaseChatModel | None = None,
    ) -> None:
        """保存配置并初始化模型; 注入模型优先于真实 DeepSeek."""
        self.settings = settings or get_settings()
        self._model = chat_model or self._build_model()
        self._timeout_seconds = float(self.settings.agent_llm_timeout_seconds)

    @property
    def model_name(self) -> str:
        """当前模型名, 仅用于日志."""
        return self.settings.deepseek_model

    @property
    def base_url(self) -> str:
        """DeepSeek 兼容接口地址."""
        return self.settings.deepseek_base_url

    def _build_model(self) -> BaseChatModel:
        """校验 API Key 并构造 ChatOpenAI 客户端."""
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
        """调用 DeepSeek 并归一化文本和 token 用量.

        Args:
            system_prompt: 系统指令.
            messages: 受控历史消息.
            user_message: 当前用户问题.
            max_output_tokens: 可选本次输出上限.

        Returns:
            LLMResult.

        Raises:
            AgentLLMConfigurationError: Prompt 为空或输出上限非法.
            AgentLLMTimeoutError: 模型调用超时.
            AgentLLMUnavailableError: 供应商调用失败.
            AgentLLMResponseError: 返回文本为空.
        """
        # ① 在调用前校验配置, 不把空 Prompt 发给供应商.
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

        # ② 把内部消息类型转换为 LangChain 消息.
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

        # ③ 用 wait_for 实现 Provider 级超时, 不依赖 HTTP 客户端默认值.
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

        # ④ 空文本视为不可用回答, 避免上层把空字符串写入历史.
        text = _content_text(getattr(response, "content", "")).strip()
        if not text:
            raise AgentLLMResponseError()

        # ⑤ 兼容 usage_metadata 和供应商原始 token_usage 两种字段.
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
        """带 Tool Schema 调用模型.

        只使用调用方传入的 tools, 不接受模型自行扩展工具集合.

        Returns:
            ToolAwareResult, 可能只有 tool_calls 没有文本.
        """
        # ① 与普通生成共享基础校验.
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

        # ② bind_tools 只暴露白名单 Schema; extra_body 固定 max_tokens.
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

        # ③ 只保留结构合法的 tool call, 参数非 dict 时退化为空.
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

        # ④ 统一 token 统计, 缺失时用输入加输出兜底.
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


# 设计层别名; 具体实现是 DeepSeek 适配器.
AgentLLM = DeepSeekLLMProvider
