from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.order import Order
    from app.models.refund import Refund
    from app.models.user import User


class Payment(Base):
    """One payment attempt for an order."""

    __tablename__ = "payments"

    __table_args__ = (
        UniqueConstraint("payment_no", name="uq_payments_payment_no"),
        UniqueConstraint("order_id", name="uq_payments_order_id"),
        UniqueConstraint(
            "channel",
            "provider_trade_no",
            name="uq_payments_channel_trade_no",
        ),
        Index("ix_payments_order_status", "order_id", "status"),
        Index("ix_payments_status_created", "status", "created_at"),
        CheckConstraint("amount > 0", name="ck_payments_amount"),
        CheckConstraint(
            "refunded_amount >= 0 AND refunded_amount <= amount",
            name="ck_payments_refunded_amount",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    payment_no: Mapped[str] = mapped_column(
        mysql.VARCHAR(32, charset="ascii", collation="ascii_bin"),
        nullable=False,
    )

    order_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "orders.id",
            name="fk_payments_order",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        nullable=False,
    )

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "users.id",
            name="fk_payments_user",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        nullable=False,
    )

    channel: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
    )

    amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        server_default="PENDING",
    )

    provider_trade_no: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    refunded_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        server_default=text("0.00"),
    )

    exception_reason: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    failure_code: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    failure_message: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    paid_at: Mapped[datetime | None] = mapped_column(
        mysql.DATETIME(fsp=6),
        nullable=True,
    )

    closed_at: Mapped[datetime | None] = mapped_column(
        mysql.DATETIME(fsp=6),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        mysql.DATETIME(fsp=6),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP(6)"),
    )

    updated_at: Mapped[datetime] = mapped_column(
        mysql.DATETIME(fsp=6),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)"),
    )

    order: Mapped["Order"] = relationship(
        back_populates="payment",
    )

    user: Mapped["User"] = relationship(
        foreign_keys=[user_id],
    )

    refunds: Mapped[list["Refund"]] = relationship(
        back_populates="payment",
    )
