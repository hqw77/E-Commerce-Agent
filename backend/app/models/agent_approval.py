"""Agent 高风险审批审计模型.

文件职责:
- 持久化审批计划, 审批状态和执行结果.
- 为管理员审批中心和消费者审批查询提供数据.
- 作为 Redis pending 过期后的审计来源.

核心边界:
Redis 只保存短期 pending; MySQL 这张表是审批状态的权威源.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AgentApproval(Base):
    """一条等待或已经完成审批的高风险 Agent 计划."""

    __tablename__ = "agent_approvals"

    __table_args__ = (
        Index("ix_agent_approvals_requester", "requester_id"),
        Index("ix_agent_approvals_status_created", "status", "created_at"),
        Index("ix_agent_approvals_expires_at", "expires_at"),
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'executed', 'failed', 'expired')",
            name="ck_agent_approvals_status",
        ),
    )

    # 内部主键与对外审批编号分离.
    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )
    approval_id: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
    )
    # 发起人和审批人分开保存, 便于审计职责分离.
    requester_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    approver_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    conversation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    thread_id: Mapped[str] = mapped_column(String(64), nullable=False)
    operation: Mapped[str] = mapped_column(String(32), nullable=False)
    resource_no: Mapped[str] = mapped_column(String(64), nullable=False)
    # 参数和前后快照用于审批详情及执行前重新校验.
    arguments: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    before_data: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    planned_data: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    action_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default="pending",
    )
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        onupdate=text("CURRENT_TIMESTAMP"),
    )
