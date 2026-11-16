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
    from app.models.order_item import OrderItem
    from app.models.payment import Payment
    from app.models.refund import Refund
    from app.models.user import User


class Order(Base):
    """Customer order and its payment/fulfillment summary."""

    __tablename__ = "orders"

    __table_args__ = (
        UniqueConstraint("order_no", name="uq_orders_order_no"),
        UniqueConstraint(
            "user_id",
            "idempotency_key",
            name="uq_orders_user_idempotency",
        ),
        Index("ix_orders_user_created", "user_id", "created_at"),
        Index("ix_orders_status_expires", "status", "expires_at"),
        Index("ix_orders_created_at", "created_at"),
        Index("ix_orders_tracking_no", "tracking_no"),
        CheckConstraint("total_amount > 0", name="ck_orders_total_amount"),
        CheckConstraint(
            "paid_amount >= 0 AND paid_amount <= total_amount",
            name="ck_orders_paid_amount",
        ),
        CheckConstraint(
            "refunded_amount >= 0 AND refunded_amount <= paid_amount",
            name="ck_orders_refunded_amount",
        ),
        CheckConstraint(
            "fulfillment_status IN ('UNSHIPPED', 'SHIPPED', 'DELIVERED', 'COMPLETED')",
            name="ck_orders_fulfillment_status",
        ),
        CheckConstraint(
            "(shipping_carrier IS NULL AND tracking_no IS NULL) OR "
            "(shipping_carrier IS NOT NULL AND tracking_no IS NOT NULL)",
            name="ck_orders_shipping_pair",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    order_no: Mapped[str] = mapped_column(
        mysql.VARCHAR(32, charset="ascii", collation="ascii_bin"),
        nullable=False,
    )

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "users.id",
            name="fk_orders_user",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        server_default="PENDING_PAYMENT",
    )

    payment_status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        server_default="UNPAID",
    )

    fulfillment_status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        server_default="UNSHIPPED",
    )

    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )

    paid_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        server_default=text("0.00"),
    )

    refunded_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        server_default=text("0.00"),
    )

    currency: Mapped[str] = mapped_column(
        mysql.CHAR(3),
        nullable=False,
        server_default="CNY",
    )

    receiver_name: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    receiver_phone: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )

    receiver_address: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    customer_remark: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    idempotency_key: Mapped[str] = mapped_column(
        mysql.VARCHAR(128, charset="ascii", collation="ascii_bin"),
        nullable=False,
    )

    request_fingerprint: Mapped[str] = mapped_column(
        mysql.CHAR(64, charset="ascii", collation="ascii_bin"),
        nullable=False,
    )

    expires_at: Mapped[datetime] = mapped_column(
        mysql.DATETIME(fsp=6),
        nullable=False,
    )

    paid_at: Mapped[datetime | None] = mapped_column(
        mysql.DATETIME(fsp=6),
        nullable=True,
    )

    shipped_at: Mapped[datetime | None] = mapped_column(
        mysql.DATETIME(fsp=6),
        nullable=True,
    )

    delivered_at: Mapped[datetime | None] = mapped_column(
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

    closed_at: Mapped[datetime | None] = mapped_column(
        mysql.DATETIME(fsp=6),
        nullable=True,
    )

    cancel_reason: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    close_reason: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    shipping_carrier: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    tracking_no: Mapped[str | None] = mapped_column(
        String(64),
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

    user: Mapped["User"] = relationship(
        foreign_keys=[user_id],
    )

    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order",
    )

    payment: Mapped["Payment | None"] = relationship(
        back_populates="order",
        uselist=False,
    )

    after_sales: Mapped[list["AfterSale"]] = relationship(
        back_populates="order",
    )

    refunds: Mapped[list["Refund"]] = relationship(
        back_populates="order",
    )
