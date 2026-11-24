
"""Refresh Token 会话模型.

Refresh Token 本身是不透明随机串, 数据库只保存 SHA-256. family_id 用于把
一次登录产生的轮换链归为一组, 检测重放时可以整体撤销.
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RefreshSession(Base):
    """可撤销, 可轮换的 Refresh Token 会话记录."""

    __tablename__ = "refresh_sessions"

    # 按用户, family 和过期时间建立索引, 支持撤销和过期清理.
    __table_args__ = (
        Index("ix_refresh_sessions_user_id", "user_id"),
        Index("ix_refresh_sessions_family_id", "family_id"),
        Index("ix_refresh_sessions_expires_at", "expires_at"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    # 同一次登录的 Refresh 轮换链共享 family_id.
    family_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
    )

    # 只保存 SHA-256, 数据库泄露时不能直接还原 Refresh Token.
    token_hash: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
    )

    # 已消费或撤销的 token 不会删除, 以便识别重放行为.
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    # 指向轮换后的新会话, 便于追踪 token 链.
    replaced_by_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("refresh_sessions.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
    )
