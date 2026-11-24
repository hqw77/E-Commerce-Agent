"""支付模型.

payments 保存订单的支付尝试和渠道状态. 一个订单最多一条支付记录,
支付成功, 失败, 关闭和退款进度分别记录, 便于处理回调和迟到支付.
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
    from app.models.order import Order
    from app.models.refund import Refund
    from app.models.user import User


class Payment(Base):
    """订单支付记录, 一个订单最多对应一条."""

    __tablename__ = "payments"

    # order_id 唯一保证一个订单只有一条支付记录; provider_trade_no 用于回调幂等.
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

    # 对外支付号, 与第三方 out_trade_no 对应.
    payment_no: Mapped[str] = mapped_column(
        mysql.VARCHAR(32, charset="ascii", collation="ascii_bin"),
        nullable=False,
    )

    # 支付必须绑定订单, 防止脱离订单创建孤立资金记录.
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

    # 支付渠道, 例如 MOCK/ALIPAY; 不同渠道的回调和退款流程不同.
    channel: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
    )

    amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )

    # PENDING/SUCCESS/FAILED/CLOSED/PARTIALLY_REFUNDED/REFUNDED 等状态.
    status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        server_default="PENDING",
    )

    # 第三方交易号, 回调验签后写入, 也是重复回调识别依据.
    provider_trade_no: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    # 已退款金额, 由退款服务维护, 不能超过支付金额.
    refunded_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        server_default=text("0.00"),
    )

    # 记录 LATE_PAYMENT 等异常原因, 不与正常支付状态混在一起.
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
