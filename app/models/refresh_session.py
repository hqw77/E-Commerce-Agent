
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
    """Persisted refresh-token session history."""

    __tablename__ = "refresh_sessions"

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

    family_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
    )

    token_hash: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
    )

    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

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
