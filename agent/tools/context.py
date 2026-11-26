"""Tool 执行时的单次请求上下文.

文件职责:
- 把用户, 数据库会话和确认存储传给 Tool handler.
- 让 Tool 使用后端可信身份, 不接受模型传入的 user_id.

核心边界:
Context 是运行时对象, 不进入 AgentState.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.core.config import Settings
from app.models.user import User
from sqlalchemy.ext.asyncio import AsyncSession

from agent.observability.trace import TraceRecorder
from agent.tools.confirmation import ConfirmationStore


@dataclass(slots=True)
class ToolContext:
    """Tool handler 的受信任依赖.

    Args:
        user: 当前登录用户; 模型不能覆盖.
        session: 本次请求的数据库会话.
        settings: 应用配置.
        conversation_id: 当前会话 ID.
        confirmation_store: 用户确认记录存储.
        trace: 当前请求 Trace.
        route: 当前 Graph 路由.
    """

    user: User
    session: AsyncSession
    settings: Settings
    conversation_id: UUID
    confirmation_store: ConfirmationStore
    trace: TraceRecorder | None = None
    route: str | None = None
