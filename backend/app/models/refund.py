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
    from app.models.after_sale import AfterSale
    from app.models.order import Order
    from app.models.payment import Payment
    from app.models.user import User


class Refund(Base):
    """Refund request against one payment."""

    __tablename__ = "refunds"

    __table_args__ = (
        UniqueConstraint("refund_no", name="uq_refunds_refund_no"),
        UniqueConstraint(
            "payment_id",
            "idempotency_key",
            name="uq_refunds_payment_idempotency",
        ),
        UniqueConstraint(
            "after_sales_id",
            name="uq_refunds_after_sales_id",
        ),
        Index("ix_refunds_order_status", "order_id", "status"),
        Index("ix_refunds_payment_status", "payment_id", "status"),
        CheckConstraint("amount > 0", name="ck_refunds_amount"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    refund_no: Mapped[str] = mapped_column(
        mysql.VARCHAR(32, charset="ascii", collation="ascii_bin"),
        nullable=False,
    )

    order_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "orders.id",
            name="fk_refunds_order",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        nullable=False,
    )

    payment_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "payments.id",
            name="fk_refunds_payment",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        nullable=False,
    )

    after_sales_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "after_sales.id",
            name="fk_refunds_after_sales",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        nullable=True,
    )

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "users.id",
            name="fk_refunds_user",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        nullable=False,
    )

    amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )

    reason: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    channel: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        server_default="PENDING",
    )

    provider_refund_no: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    idempotency_key: Mapped[str] = mapped_column(
        mysql.VARCHAR(128, charset="ascii", collation="ascii_bin"),
        nullable=False,
    )

    failure_code: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    failure_message: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    requested_at: Mapped[datetime] = mapped_column(
        mysql.DATETIME(fsp=6),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP(6)"),
    )

    processed_at: Mapped[datetime | None] = mapped_column(
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
        back_populates="refunds",
    )

    payment: Mapped["Payment"] = relationship(
        back_populates="refunds",
    )

    after_sale: Mapped["AfterSale | None"] = relationship(
        back_populates="refund",
        uselist=False,
    )

    user: Mapped["User"] = relationship(
        foreign_keys=[user_id],
    )
