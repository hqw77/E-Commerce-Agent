"""Agent 请求级运行时.

文件职责:
- 为一次聊天请求创建可信 Context.
- 执行安全检查, 限流, 会话锁和超时控制.
- 调用编译好的 LangGraph, 并把结果转换成 ChatResult.

核心流程:
chat -> safety -> rate limit -> conversation lock -> graph.ainvoke
     -> trace/result -> release lock.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from app.core.config import Settings, get_settings
from app.core.exceptions import AppException
from app.models.user import User
from app.services.rag.retrieval_service import KnowledgeRetrievalService
from app.services.rag.runtime import get_embedding_provider, get_vector_store
from sqlalchemy.ext.asyncio import AsyncSession

from agent.context import AgentRuntimeContext
from agent.conversation import ConversationStore, new_conversation_id
from agent.exceptions import (
    AgentConversationBusyError,
    AgentDisabledError,
    AgentExecutionTimeoutError,
    AgentInternalError,
)
from agent.graph import COMPILED_AGENT_GRAPH
from agent.llm import AgentLLM, DeepSeekLLMProvider
from agent.observability.store import get_default_trace_collector
from agent.observability.trace import (
    TraceCollector,
    TraceRecorder,
)
from agent.rate_limit import RedisRateLimiter
from agent.safety import SafetyPipeline
from agent.state import SourceRef
from agent.tools import TOOL_REGISTRY
from agent.tools.confirmation import ConfirmationStore
from agent.tools.executor import ToolExecutor
from agent.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

# 进程级缓存. 未配置时由 get_agent_llm 延迟创建, 避免导入阶段读取密钥.
_agent_llm: AgentLLM | None = None


def get_agent_llm(settings: Settings | None = None) -> AgentLLM:
    """返回进程级 Agent LLM.

    Args:
        settings: 可选的配置覆盖, 测试中可注入.

    Returns:
        DeepSeek-backed AgentLLM 实例.
    """
    global _agent_llm
    if _agent_llm is None:
        _agent_llm = DeepSeekLLMProvider(settings or get_settings())
    return _agent_llm


@dataclass(frozen=True, slots=True)
class ChatResult:
    """一次 Agent 聊天的最终结果.

    Args:
        conversation_id: 会话 ID.
        message_id: 本次回答消息 ID.
        answer: 最终回答文本.
        sources: 后端构造的 RAG 来源.
        created_at: 结果生成时间.
        pending_action: 需要用户确认或管理员审批的待办.
        trace_id: 本次请求的 Trace ID.
    """

    conversation_id: UUID
    message_id: UUID
    answer: str
    sources: list[SourceRef]
    created_at: datetime
    pending_action: dict[str, Any] | None = None
    trace_id: str | None = None


class AgentRuntime:
    """持有一次请求的可信依赖, 并串行化同一会话."""

    def __init__(
        self,
        session: AsyncSession,
        user: User,
        settings: Settings | None = None,
        *,
        llm: AgentLLM | None = None,
        retrieval: KnowledgeRetrievalService | None = None,
        conversation_store: ConversationStore | None = None,
        rate_limiter: RedisRateLimiter | None = None,
        graph: Any | None = None,
        tool_registry: ToolRegistry | None = None,
        tool_executor: ToolExecutor | None = None,
        confirmation_store: ConfirmationStore | None = None,
        trace_collector: TraceCollector | None = None,
    ) -> None:
        """创建一次请求的运行时.

        所有可选参数都用于测试注入; 生产调用通常只传 session 和 user.
        """
        self.session = session
        self.user = user
        self.settings = settings or get_settings()
        self.llm = llm or get_agent_llm(self.settings)
        self.retrieval = retrieval or KnowledgeRetrievalService(
            session,
            self.settings,
            embedding=get_embedding_provider(self.settings),
            vector_store=get_vector_store(self.settings),
        )
        self.conversation_store = conversation_store or ConversationStore(
            self.settings
        )
        self.rate_limiter = rate_limiter or RedisRateLimiter(self.settings)
        self.graph = graph or COMPILED_AGENT_GRAPH
        self.tool_registry = tool_registry or TOOL_REGISTRY
        self.confirmation_store = confirmation_store or ConfirmationStore(
            self.settings
        )
        self.tool_executor = tool_executor or ToolExecutor(
            self.tool_registry,
            max_calls=self.settings.agent_max_tool_calls_per_turn,
        )
        self.trace_collector = trace_collector

    async def chat(
        self,
        *,
        message: str,
        conversation_id: UUID | None = None,
    ) -> ChatResult:
        """执行一次 Agent 聊天请求.

        Args:
            message: 用户原始消息.
            conversation_id: 续聊会话 ID; 为空时新建会话.

        Returns:
            ChatResult, 包含回答, 来源, pending action 和 trace_id.

        Raises:
            AgentDisabledError: Agent 功能关闭.
            AgentConversationBusyError: 同一会话已有请求在执行.
            AgentExecutionTimeoutError: 整张图超过执行时限.
            AgentInternalError: 未分类的内部错误.
        """
        # ① 功能开关, 输入安全和用户级限流.
        if not self.settings.agent_enabled:
            raise AgentDisabledError()

        safety_input = SafetyPipeline(self.settings).check_input(message)
        normalized = safety_input.message
        await self.rate_limiter.check(self.user.id)

        # ② 为本次会话获取分布式锁, 防止同一会话并发写历史.
        new_conversation = conversation_id is None
        active_conversation_id = conversation_id or new_conversation_id()
        lock_token = uuid4().hex
        if not await self.conversation_store.acquire_lock(
            user_id=self.user.id,
            conversation_id=active_conversation_id,
            token=lock_token,
        ):
            raise AgentConversationBusyError()

        # ③ 创建 Trace 和请求级可信 Context.
        request_id = uuid4().hex
        trace_id = request_id
        started_at = datetime.now(UTC)
        started_perf = time.perf_counter()
        trace = TraceRecorder(
            trace_id=trace_id,
            request_id=request_id,
            conversation_id=str(active_conversation_id),
            user_id=self.user.id,
            collector=self.trace_collector or get_default_trace_collector(),
        )
        trace.emit("request_start", execution_status="STARTED")
        trace.emit(
            "safety_input",
            execution_status="SUCCESS",
            risk_level=(
                "MEDIUM" if safety_input.injection_suspected else "LOW"
            ),
            result_summary={
                "injection_suspected": safety_input.injection_suspected,
                "check_degraded": safety_input.check_degraded,
            },
            error_code=(
                "AGENT_SAFETY_CHECK_DEGRADED"
                if safety_input.check_degraded
                else None
            ),
        )
        # 可信依赖只进入 Context, 不写入可序列化 State.
        context = AgentRuntimeContext(
            request_id=request_id,
            user=self.user,
            session=self.session,
            settings=self.settings,
            llm=self.llm,
            retrieval=self.retrieval,
            conversation_store=self.conversation_store,
            lock_token=lock_token,
            is_new_conversation=new_conversation,
            tool_executor=self.tool_executor,
            confirmation_store=self.confirmation_store,
            trace_id=trace_id,
            trace=trace,
        )
        # ④ 组装 State 和 Context. State 只放可序列化值, Context 放运行期依赖.
        # 每次请求把身份, 会话和审批默认值写入 State; 运行期对象仍留在 Context.
        initial_state = {
            "request_id": request_id,
            "trace_id": trace_id,
            "conversation_id": str(active_conversation_id),
            "thread_id": str(active_conversation_id),
            "user_id": self.user.id,
            "user_role": "admin" if self.user.is_admin else "user",
            "parameters": {},
            "approval_required": False,
            "approval_id": None,
            "approval_status": None,
            "user_message": normalized,
            "started_at": started_at,
        }

        try:
            # ⑤ 用超时包住整张图, 防止单个请求长期占用会话锁.
            async with asyncio.timeout(
                self.settings.agent_max_execution_seconds
            ):
                final_state = await self.graph.ainvoke(
                    initial_state,
                    context=context,
                )
        except TimeoutError as exc:
            trace.emit(
                "request_error",
                execution_status="ERROR",
                duration_ms=round(
                    (time.perf_counter() - started_perf) * 1000,
                    2,
                ),
                error_code="AGENT_EXECUTION_TIMEOUT",
            )
            raise AgentExecutionTimeoutError() from exc
        except AgentInternalError as exc:
            trace.emit(
                "request_error",
                execution_status="ERROR",
                duration_ms=round(
                    (time.perf_counter() - started_perf) * 1000,
                    2,
                ),
                error_code=exc.code,
            )
            raise
        except Exception as exc:
            code = (
                exc.code
                if isinstance(exc, AppException)
                else "AGENT_INTERNAL_ERROR"
            )
            trace.emit(
                "request_error",
                execution_status="ERROR",
                duration_ms=round(
                    (time.perf_counter() - started_perf) * 1000,
                    2,
                ),
                error_code=code,
            )
            if isinstance(exc, AppException):
                raise
            logger.error(
                "agent_execution_failed",
                extra={
                    "request_id": request_id,
                    "trace_id": trace_id,
                    "error_type": type(exc).__name__,
                },
            )
            raise AgentInternalError() from exc
        finally:
            # ⑥ 无论成功或失败都释放锁, 避免会话永久阻塞.
            await self.conversation_store.release_lock(
                user_id=self.user.id,
                conversation_id=active_conversation_id,
                token=lock_token,
            )

        # ⑦ 记录结束事件并转换成 API 层使用的 ChatResult.
        trace.emit(
            "request_end",
            execution_status="SUCCESS",
            duration_ms=round(
                (time.perf_counter() - started_perf) * 1000,
                2,
            ),
            result_summary={
                "answer_length": len(str(final_state["answer"])),
                "source_count": len(final_state.get("sources", [])),
                "pending_action": bool(final_state.get("pending_action")),
                "total_tokens": getattr(
                    final_state.get("token_usage"),
                    "total_tokens",
                    0,
                ),
            },
        )
        return ChatResult(
            conversation_id=active_conversation_id,
            message_id=uuid4(),
            answer=str(final_state["answer"]),
            sources=list(final_state.get("sources", [])),
            created_at=datetime.now(UTC),
            pending_action=final_state.get("pending_action"),
            trace_id=trace_id,
        )
