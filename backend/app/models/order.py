"""订单模型.

orders 保存订单头, 金额汇总以及支付/履约状态. 具体商品快照在 order_items,
支付在 payments, 售后在 after_sales. 订单状态和履约状态分开建模, 避免把
支付成功, 发货, 送达混成单一状态.
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
    from app.models.order_item import OrderItem
    from app.models.payment import Payment
    from app.models.refund import Refund
    from app.models.user import User


class Order(Base):
    """订单头, 聚合支付, 履约和售后关系."""

    __tablename__ = "orders"

    # 订单号唯一; user_id + idempotency_key 防止重复提交创建重复订单.
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

    # 对外订单号使用 ascii_bin, 保证大小写敏感且便于索引.
    order_no: Mapped[str] = mapped_column(
        mysql.VARCHAR(32, charset="ascii", collation="ascii_bin"),
        nullable=False,
    )

    # 订单归属用户, RESTRICT 防止误删有订单的用户.
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

    # 主状态: PENDING_PAYMENT/PAID/CANCELLED/CLOSED/COMPLETED.
    status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        server_default="PENDING_PAYMENT",
    )

    # 支付状态独立于主状态, 用于表达部分退款和迟到支付等情况.
    payment_status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        server_default="UNPAID",
    )

    # 履约状态: UNSHIPPED/SHIPPED/DELIVERED/COMPLETED.
    fulfillment_status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        server_default="UNSHIPPED",
    )

    # 订单应付金额, 由下单时 SKU 快照计算, 不随后续调价变化.
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

    # 客户端幂等键; 与 request_fingerprint 一起区分重试和参数冲突.
    idempotency_key: Mapped[str] = mapped_column(
        mysql.VARCHAR(128, charset="ascii", collation="ascii_bin"),
        nullable=False,
    )

    # 请求参数哈希; 同一幂等键但参数变化时必须返回冲突, 不能复用旧订单.
    request_fingerprint: Mapped[str] = mapped_column(
        mysql.CHAR(64, charset="ascii", collation="ascii_bin"),
        nullable=False,
    )

    # 待支付截止时间; 超时任务据此关闭订单并释放库存.
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

    # 关系字段只表达导航, 业务删除策略由 ForeignKey 和 Service 决定.
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
