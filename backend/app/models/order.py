"""订单 ORM 模型.

文件职责:
- 保存订单头, 收货信息, 金额汇总和状态时间.
- 关联订单项, 支付, 售后和退款.

核心边界:
订单主状态, 支付状态和履约状态分开建模.
订单项保存下单时的商品/价格快照, 不随后续调价变化.
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
    from app.models.user import User


class Order(Base):
    """订单头, 聚合履约和售后关系."""

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
        Index("ix_orders_created_at", "created_at"),
        Index("ix_orders_tracking_no", "tracking_no"),
        CheckConstraint("total_amount > 0", name="ck_orders_total_amount"),
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

    # 以下时间字段分别记录履约各阶段, 避免用单一 updated_at 推断业务进度.
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

    # updated_at 只表示行更新时间, 不能替代业务状态时间.
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

    after_sales: Mapped[list["AfterSale"]] = relationship(
        back_populates="order",
    )
