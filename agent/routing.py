"""Agent 的确定性意图预检查与路由辅助.

文件职责:
- 用正则先拦截明确的支持/不支持请求.
- 规则未命中时调用 LLM 做意图分类.
- 把旧 Intent 映射为新的 route 词表和 Graph 节点名.

核心流程:
obvious_* 规则 -> LLM classify -> AgentIntent
-> route_name_for_intent -> node_for_route -> Graph 条件边.
"""

from __future__ import annotations

import json
import re

from agent.exceptions import AgentIntentError
from agent.llm import AgentLLM
from agent.prompts import INTENT_SYSTEM_PROMPT
from agent.state import AgentIntent, AgentRoute, AgentState

# 明确不支持或高风险的写操作. 这些规则先于 LLM 执行, 防止模型误分类.
_UNSUPPORTED_ACTION_PATTERNS = (
    re.compile(r"申请\s*退款"),
    re.compile(r"发起\s*支付"),
    re.compile(r"创建\s*订单"),
    re.compile(r"帮我\s*退款"),
    re.compile(r"refund\s+(my\s+)?order", re.IGNORECASE),
    re.compile(r"change\s+(the\s+)?stock", re.IGNORECASE),
)

# 需要进入 Prepare/审批或用户确认流程的请求.
_WORKFLOW_PATTERNS = (
    re.compile(r"(取消|关闭)\s*订单"),
    re.compile(r"申请\s*售后"),
    re.compile(r"售后申请"),
    re.compile(r"(调整|修改|增加|减少|补充)\s*(SKU\s*)?库存", re.IGNORECASE),
)

# 明确的只读查询直接走 Tool, 减少一次 LLM 分类调用.
_TOOL_PATTERNS = (
    re.compile(r"查询.*订单"),
    re.compile(r"我的订单"),
    re.compile(r"我的售后"),
    re.compile(r"售后记录"),
    re.compile(r"商品|SKU|库存", re.IGNORECASE),
)


def obvious_unsupported_action(message: str) -> bool:
    """判断消息是否命中明确不支持的高风险操作.

    Args:
        message: 用户原始消息.

    Returns:
        True 表示应直接路由到 UNSUPPORTED_ACTION.
    """
    return any(pattern.search(message) for pattern in _UNSUPPORTED_ACTION_PATTERNS)


def obvious_workflow_action(message: str) -> bool:
    """判断消息是否应进入 Prepare/审批工作流.

    Args:
        message: 用户原始消息.

    Returns:
        True 表示应路由到 WORKFLOW.
    """
    return any(pattern.search(message) for pattern in _WORKFLOW_PATTERNS)


def obvious_tool_action(message: str) -> bool:
    """判断消息是否是可以直接走 READ Tool 的只读查询.

    Args:
        message: 用户原始消息.

    Returns:
        True 表示应路由到 TOOL.
    """
    return any(pattern.search(message) for pattern in _TOOL_PATTERNS)


def _parse_intent(text: str) -> AgentIntent | None:
    """解析 LLM 返回的 Intent.

    Args:
        text: LLM 原始文本, 可能是纯标签或 JSON.

    Returns:
        合法 AgentIntent; 无法解析时返回 None.
    """
    normalized = text.strip()
    if normalized in {
        "GENERAL",
        "RAG",
        "KNOWLEDGE",
        "TOOL",
        "WORKFLOW",
        "UNSUPPORTED_ACTION",
    }:
        return normalized  # type: ignore[return-value]

    try:
        value = json.loads(normalized)
    except (TypeError, ValueError):
        return None

    if isinstance(value, dict):
        candidate = value.get("intent")
        if candidate in {
            "GENERAL",
            "RAG",
            "KNOWLEDGE",
            "TOOL",
            "WORKFLOW",
            "UNSUPPORTED_ACTION",
        }:
            return candidate  # type: ignore[return-value]
    return None


async def classify_intent(
    *,
    llm: AgentLLM,
    message: str,
) -> AgentIntent:
    """识别用户意图, 规则优先于 LLM.

    Args:
        llm: 意图分类使用的模型客户端.
        message: 用户原始消息.

    Returns:
        合法的 AgentIntent.

    Raises:
        AgentIntentError: LLM 返回了无法识别的标签.
    """
    # ① 先跑确定性规则; 命中后不消耗 LLM Token.
    if obvious_unsupported_action(message):
        return "UNSUPPORTED_ACTION"
    if obvious_workflow_action(message):
        return "WORKFLOW"
    if obvious_tool_action(message):
        return "TOOL"

    # ② 规则未命中时才调用 LLM, 并限制输出长度.
    result = await llm.generate(
        system_prompt=INTENT_SYSTEM_PROMPT,
        user_message=message,
        max_output_tokens=32,
    )
    # ③ 模型输出必须通过白名单解析, 不能直接信任.
    intent = _parse_intent(result.text)
    if intent is None:
        raise AgentIntentError()
    return intent


def route_intent(state: AgentState) -> str:
    """把旧 Intent 映射为旧版 Graph 节点名.

    Args:
        state: 至少包含 intent 的 AgentState.

    Returns:
        旧版条件边使用的节点名.
    """
    intent = state.get("intent")
    if intent == "GENERAL":
        return "general_answer"
    if intent in {"RAG", "KNOWLEDGE"}:
        return "retrieve_knowledge"
    if intent == "TOOL":
        return "plan_tool"
    if intent == "WORKFLOW":
        return "plan_workflow"
    return "unsupported_action"


# 旧 Intent 到新 route 的兼容映射, 避免一次性改动 Prompt 和测试.
def route_name_for_intent(intent: object) -> AgentRoute:
    """把旧大写 Intent 映射为新的 route 词表.

    Args:
        intent: AgentIntent 或兼容的 KNOWLEDGE 别名.

    Returns:
        新的 AgentRoute.
    """
    if intent == "GENERAL":
        return "general"
    if intent in {"RAG", "KNOWLEDGE"}:
        return "rag"
    if intent == "TOOL":
        return "tool"
    if intent == "WORKFLOW":
        return "workflow"
    return "unsupported"


def route_for_state(state: AgentState) -> AgentRoute:
    """优先使用显式 route, 缺失时回退到旧 intent.

    Args:
        state: 当前 AgentState.

    Returns:
        规范化后的 AgentRoute.
    """
    route = state.get("route")
    if route in {"general", "rag", "tool", "workflow", "unsupported"}:
        return route  # type: ignore[return-value]
    return route_name_for_intent(state.get("intent"))


# Graph 的条件边只认节点名, 这里集中维护 route 到节点的映射.
def node_for_route(state: AgentState) -> str:
    """把 route 映射为 Graph 条件边需要的节点名.

    Args:
        state: 至少包含 route 或 intent 的 AgentState.

    Returns:
        Graph 节点名.
    """
    return {
        "general": "general_answer",
        "rag": "retrieve_knowledge",
        "tool": "plan_tool",
        "workflow": "plan_workflow",
        "unsupported": "unsupported_action",
    }[route_for_state(state)]
