from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.order import Order
    from app.models.order_item import OrderItem
    from app.models.refund import Refund
    from app.models.user import User


class AfterSale(Base):
    """After-sales request for one order item."""

    __tablename__ = "after_sales"

    __table_args__ = (
        UniqueConstraint(
            "after_sales_no",
            name="uq_after_sales_after_sales_no",
        ),
        UniqueConstraint(
            "user_id",
            "idempotency_key",
            name="uq_after_sales_user_idempotency",
        ),
        Index("ix_after_sales_user_status", "user_id", "status"),
        Index("ix_after_sales_order_id", "order_id"),
        Index(
            "ix_after_sales_order_item_status",
            "order_item_id",
            "status",
        ),
        Index("ix_after_sales_status_created", "status", "created_at"),
        CheckConstraint("quantity > 0", name="ck_after_sales_quantity"),
        CheckConstraint(
            "requested_amount > 0",
            name="ck_after_sales_requested_amount",
        ),
        CheckConstraint(
            "approved_amount IS NULL OR approved_amount = requested_amount",
            name="ck_after_sales_approved_amount",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    after_sales_no: Mapped[str] = mapped_column(
        mysql.VARCHAR(32, charset="ascii", collation="ascii_bin"),
        nullable=False,
    )

    order_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "orders.id",
            name="fk_after_sales_order",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        nullable=False,
    )

    order_item_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "order_items.id",
            name="fk_after_sales_order_item",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        nullable=False,
    )

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "users.id",
            name="fk_after_sales_user",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        nullable=False,
    )

    type: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default="PENDING_REVIEW",
    )

    quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    requested_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )

    approved_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2),
        nullable=True,
    )

    reason: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    evidence_urls: Mapped[list[str] | None] = mapped_column(
        JSON,
        nullable=True,
    )

    review_note: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    reviewed_by: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "users.id",
            name="fk_after_sales_reviewer",
            ondelete="SET NULL",
            onupdate="RESTRICT",
        ),
        nullable=True,
    )

    reviewed_at: Mapped[datetime | None] = mapped_column(
        mysql.DATETIME(fsp=6),
        nullable=True,
    )

    return_carrier: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    return_tracking_no: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    returned_at: Mapped[datetime | None] = mapped_column(
        mysql.DATETIME(fsp=6),
        nullable=True,
    )

    received_by: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "users.id",
            name="fk_after_sales_receiver",
            ondelete="SET NULL",
            onupdate="RESTRICT",
        ),
        nullable=True,
    )

    received_at: Mapped[datetime | None] = mapped_column(
        mysql.DATETIME(fsp=6),
        nullable=True,
    )

    replacement_carrier: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    replacement_tracking_no: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    replacement_shipped_at: Mapped[datetime | None] = mapped_column(
        mysql.DATETIME(fsp=6),
        nullable=True,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        mysql.DATETIME(fsp=6),
        nullable=True,
    )

    cancelled_at: Mapped[datetime | None] = mapped_column(
        mysql.DATETIME(fsp=6),
        nullable=True,
    )

    idempotency_key: Mapped[str] = mapped_column(
        mysql.VARCHAR(128, charset="ascii", collation="ascii_bin"),
        nullable=False,
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
        back_populates="after_sales",
    )

    order_item: Mapped["OrderItem"] = relationship(
        back_populates="after_sales",
    )

    user: Mapped["User"] = relationship(
        foreign_keys=[user_id],
    )

    reviewer: Mapped["User | None"] = relationship(
        foreign_keys=[reviewed_by],
    )

    receiver: Mapped["User | None"] = relationship(
        foreign_keys=[received_by],
    )

    refund: Mapped["Refund | None"] = relationship(
        back_populates="after_sale",
        uselist=False,
    )
