"""Deterministic intent pre-checks and routing helpers."""

from __future__ import annotations

import json
import re

from agent.exceptions import AgentIntentError
from agent.llm import AgentLLM
from agent.prompts import INTENT_SYSTEM_PROMPT
from agent.state import AgentIntent, AgentState

_UNSUPPORTED_ACTION_PATTERNS = (
    re.compile(r"申请\s*退款"),
    re.compile(r"发起\s*支付"),
    re.compile(r"修改\s*库存"),
    re.compile(r"创建\s*订单"),
    re.compile(r"帮我\s*退款"),
    re.compile(r"refund\s+(my\s+)?order", re.IGNORECASE),
    re.compile(r"change\s+(the\s+)?stock", re.IGNORECASE),
)

_TOOL_PATTERNS = (
    re.compile(r"(取消|关闭)\s*订单"),
    re.compile(r"申请\s*售后"),
    re.compile(r"查询.*订单"),
    re.compile(r"我的订单"),
    re.compile(r"我的售后"),
    re.compile(r"售后记录"),
    re.compile(r"商品|SKU|库存", re.IGNORECASE),
)


def obvious_unsupported_action(message: str) -> bool:
    """Protect the unsupported-write boundary without trusting the model."""
    return any(pattern.search(message) for pattern in _UNSUPPORTED_ACTION_PATTERNS)


def obvious_tool_action(message: str) -> bool:
    """Route clear supported business requests without relying on the model."""
    return any(pattern.search(message) for pattern in _TOOL_PATTERNS)


def _parse_intent(text: str) -> AgentIntent | None:
    normalized = text.strip()
    if normalized in {"GENERAL", "KNOWLEDGE", "TOOL", "UNSUPPORTED_ACTION"}:
        return normalized  # type: ignore[return-value]

    try:
        value = json.loads(normalized)
    except (TypeError, ValueError):
        return None

    if isinstance(value, dict):
        candidate = value.get("intent")
        if candidate in {"GENERAL", "KNOWLEDGE", "TOOL", "UNSUPPORTED_ACTION"}:
            return candidate  # type: ignore[return-value]
    return None


async def classify_intent(
    *,
    llm: AgentLLM,
    message: str,
) -> AgentIntent:
    if obvious_unsupported_action(message):
        return "UNSUPPORTED_ACTION"
    if obvious_tool_action(message):
        return "TOOL"

    result = await llm.generate(
        system_prompt=INTENT_SYSTEM_PROMPT,
        user_message=message,
        max_output_tokens=32,
    )
    intent = _parse_intent(result.text)
    if intent is None:
        raise AgentIntentError()
    return intent


def route_intent(state: AgentState) -> str:
    intent = state.get("intent")
    if intent == "GENERAL":
        return "general_answer"
    if intent == "KNOWLEDGE":
        return "retrieve_knowledge"
    if intent == "TOOL":
        return "plan_tool"
    return "unsupported_action"
