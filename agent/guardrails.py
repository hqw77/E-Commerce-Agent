"""Agent 输入/输出护栏和上下文预算.

文件职责:
- 清洗用户输入并拒绝空消息/超长消息.
- 识别明显的 Prompt 注入特征.
- 按字符预算选择完整对话轮次和 RAG Chunk.
- 校验模型输出长度, 密钥泄漏和来源合法性.

核心边界:
这些规则是确定性的防御纵深, 不是 ACL, 不能替代后端鉴权.
"""

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

# 去掉会破坏日志或终端显示的控制字符.
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# 只作为诊断信号; 命中不代表请求一定恶意.
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

# 常见 API Key, 私钥和 JWT 形态, 用于输出泄漏检测.
_SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
)


@dataclass(frozen=True, slots=True)
class ContextSelection:
    """允许发送给模型的有限上下文.

    Args:
        history: 选中的完整对话轮次.
        rag_items: 选中的 RAG Chunk.
        context_text: 序列化后的不可信参考数据.
    """

    history: list[HistoryMessage]
    rag_items: list[RetrievalItem]
    context_text: str


def validate_user_message(message: str, settings: Settings) -> str:
    """清洗并校验用户消息.

    Args:
        message: 原始用户输入.
        settings: 输入长度配置.

    Returns:
        去掉控制字符和首尾空白后的消息.
    """
    normalized = _CONTROL_CHARS.sub("", message).strip()
    if not normalized:
        raise AgentInputInvalidError("Agent message must not be empty")
    if len(normalized) > settings.agent_max_input_chars:
        raise AgentInputInvalidError()
    return normalized


def looks_like_prompt_injection(message: str) -> bool:
    """返回启发式 Prompt 注入信号, 不承担权限判断."""
    lowered = message.casefold()
    return any(pattern in lowered for pattern in _INJECTION_PATTERNS)


def _complete_turns(
    history: list[HistoryMessage],
) -> list[tuple[HistoryMessage, HistoryMessage]]:
    """把历史拆成完整的 user/assistant 轮次."""
    turns: list[tuple[HistoryMessage, HistoryMessage]] = []
    for left, right in itertools.pairwise(history):
        if left.role == "user" and right.role == "assistant":
            turns.append((left, right))
    return turns


def _flat(turns: list[tuple[HistoryMessage, HistoryMessage]]) -> list[HistoryMessage]:
    """把轮次重新展平成消息列表."""
    return [message for turn in turns for message in turn]


def select_context(
    *,
    history: list[HistoryMessage],
    user_message: str,
    rag_items: list[RetrievalItem],
    settings: Settings,
) -> ContextSelection:
    """按字符预算选择完整轮次和完整 RAG Chunk.

    Raises:
        AgentContextBudgetExceededError: 当前问题或最新一轮已超预算.
    """
    current_length = len(user_message)
    if current_length > settings.agent_max_history_chars:
        raise AgentContextBudgetExceededError()

    # ① 至少保留最新一轮, 再从旧到新尽量补充.
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

    # ② RAG 按分数优先, 但只接受完整 Chunk, 避免截断语义.
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

    # ③ 明确标记为 untrusted, 让 Prompt 知道这些是数据不是指令.
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
    """在后端构造来源对象, 不接受模型自带来源."""
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
    """校验模型输出长度, 密钥泄漏和来源合法性.

    Returns:
        去除首尾空白后的安全回答.
    """
    normalized = answer.strip()
    if not normalized:
        raise AgentOutputRejectedError()
    if len(normalized) > settings.agent_max_output_chars:
        raise AgentOutputRejectedError("Agent output is too long")

    # ① 输出中不允许出现常见密钥/私钥/JWT.
    for pattern in _SECRET_PATTERNS:
        if pattern.search(normalized):
            raise AgentOutputRejectedError()

    # ② 来源必须来自本次实际检索结果, 防止模型编造引用.
    allowed_chunk_ids = {item.chunk_id for item in retrieved_items}
    if any(source.chunk_id not in allowed_chunk_ids for source in sources):
        raise AgentOutputRejectedError("Agent source is not in retrieved context")

    return normalized
