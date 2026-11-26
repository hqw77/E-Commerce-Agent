"""Agent 图的可序列化状态与值对象.

文件职责:
- 定义 Intent, Route 和审批状态词表.
- 定义 Graph 在每个节点之间传递的 AgentState.
- 定义对话消息, Token 用量和 RAG 来源引用.

核心边界:
AgentState 只保存可序列化数据. ORM User, AsyncSession, LLM 和 Redis
客户端属于运行时依赖, 放在 AgentRuntimeContext, 不能进入这里.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, TypedDict

from app.schemas.knowledge import RetrievalItem

# 旧 Intent 词表保留给现有 Prompt 和测试; 对外路由使用下面的 AgentRoute.
AgentIntent = Literal[
    "GENERAL",
    "RAG",
    "KNOWLEDGE",
    "TOOL",
    "WORKFLOW",
    "UNSUPPORTED_ACTION",
]

# 对外的 route 词表. 它比 Intent 少一层历史兼容, 直接对应 Graph 的执行路径.
AgentRoute = Literal["general", "rag", "tool", "workflow", "unsupported"]

# 审批生命周期. 计划正文和审计分别保存在 Redis 和 MySQL, 这里只保存状态.
ApprovalStatus = Literal[
    "pending",
    "approved",
    "rejected",
    "executed",
    "failed",
    "expired",
]


@dataclass(frozen=True, slots=True)
class HistoryMessage:
    """一条可回传给模型的历史消息.

    Args:
        role: 消息角色, 只能是 user 或 assistant.
        content: 消息正文.
    """

    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True, slots=True)
class TokenUsage:
    """一次 Agent 请求内累计的 Token 用量.

    Args:
        input_tokens: 输入 Token 数.
        output_tokens: 输出 Token 数.
        total_tokens: 输入与输出之和.
    """

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0

    def plus(self, other: TokenUsage) -> TokenUsage:
        """返回两个 TokenUsage 的逐字段之和, 不修改原对象."""
        return TokenUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
        )


@dataclass(frozen=True, slots=True)
class SourceRef:
    """后端根据 RetrievalItem 构造的可信来源引用.

    Args:
        document_id: 知识文档 ID.
        version_id: 文档版本 ID.
        chunk_id: 命中的知识片段 ID.
        title: 文档标题.
        section_title: 章节标题.
        page_number: PDF 页码.
    """

    document_id: int
    version_id: int
    chunk_id: int
    title: str
    section_title: str | None
    page_number: int | None


class AgentState(TypedDict, total=False):
    """LangGraph 在一次请求内传递的状态.

    所有字段都是可选的, 因为不同节点只返回自己负责的局部更新.
    运行时对象不能进入这里, 否则会破坏序列化和中断恢复.
    """

    # 请求身份与会话标识.
    request_id: str
    trace_id: str
    conversation_id: str
    thread_id: str
    conversation_created_at: str
    user_id: int
    user_role: Literal["user", "admin"]
    user_message: str

    # 会话历史与意图路由.
    history: list[HistoryMessage]
    intent: AgentIntent
    route: AgentRoute
    parameters: dict[str, object]

    # RAG 检索结果与拼装后的上下文.
    retrieved_items: list[RetrievalItem]
    context_text: str

    # Tool 规划与执行结果.
    tool_name: str | None
    tool_args: dict[str, object]
    tool_result: dict[str, object] | None
    tool_call_count: int
    pending_action: dict[str, object] | None

    # 库存调整 HITL 路径专用字段; 普通查询保持默认值.
    approval_required: bool
    approval_id: str | None
    approval_status: ApprovalStatus | None

    # 最终输出与观测数据.
    answer: str
    sources: list[SourceRef]
    error_code: str | None
    token_usage: TokenUsage
    started_at: datetime
