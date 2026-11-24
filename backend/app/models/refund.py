"""退款模型.

refunds 记录对某笔支付的退款请求, 金额和状态由 RefundService 维护.
退款可以来自售后审核, 也可以由管理员手工发起, 但都必须绑定原支付.
"""

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
    """针对一笔支付的退款记录, 售后退款和手工退款共用."""

    __tablename__ = "refunds"

    # payment_id + idempotency_key 防重复退款; after_sales_id 唯一防一个售后多次退款.
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

    # 退款必须指向原支付记录, 防止跨支付退款或超出可退金额.
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

    # 售后退款关联售后单; 手工退款可以为空.
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

    # 退款金额, 必须大于 0 且累计不能超过支付金额.
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

    # PENDING/PROCESSING/SUCCESS/FAILED 等退款状态.
    status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        server_default="PENDING",
    )

    # 第三方退款单号, 用于查询未知结果和防止重复提交.
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

    # 一个退款最多关联一个售后, 一个售后也最多对应一个退款.
    after_sale: Mapped["AfterSale | None"] = relationship(
        back_populates="refund",
        uselist=False,
    )

    user: Mapped["User"] = relationship(
        foreign_keys=[user_id],
    )
