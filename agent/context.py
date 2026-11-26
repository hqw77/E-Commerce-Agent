"""LangGraph 单次请求的运行时依赖容器.

文件职责:
- 保存 ORM User, AsyncSession, LLM 和 RAG 服务等请求级依赖.
- 为 Graph 节点提供可信上下文, 避免节点自己读取全局状态.

核心边界:
Context 只在一次 graph invocation 内有效, 不进入可序列化的 AgentState.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings
from app.models.user import User
from app.services.rag.retrieval_service import KnowledgeRetrievalService
from sqlalchemy.ext.asyncio import AsyncSession

from agent.conversation import ConversationStore
from agent.llm import AgentLLM
from agent.observability.trace import TraceRecorder
from agent.tools.confirmation import ConfirmationStore
from agent.tools.executor import ToolExecutor


@dataclass(slots=True)
class AgentRuntimeContext:
    """一次 Agent 请求的受信任依赖.

    这些对象不能放进 AgentState, 因为其中包含数据库连接和客户端句柄.

    Args:
        request_id: 本次请求 ID.
        user: 当前登录用户 ORM 对象.
        session: 本次请求的异步数据库会话.
        settings: 应用配置.
        llm: Agent 使用的模型客户端.
        retrieval: RAG 检索服务.
        conversation_store: Redis 会话存储.
        lock_token: 当前会话锁令牌.
        is_new_conversation: 是否是新建会话.
        tool_executor: Tool 执行器.
        confirmation_store: 用户确认记录存储.
        trace_id: Trace 关联 ID.
        trace: 当前请求的 Trace 记录器.
    """

    request_id: str
    user: User
    session: AsyncSession
    settings: Settings
    llm: AgentLLM
    retrieval: KnowledgeRetrievalService
    conversation_store: ConversationStore
    lock_token: str
    is_new_conversation: bool
    tool_executor: ToolExecutor | None = None
    confirmation_store: ConfirmationStore | None = None
    trace_id: str | None = None
    trace: TraceRecorder | None = None
