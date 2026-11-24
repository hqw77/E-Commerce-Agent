"""SKU 当前库存模型.

inventory 只保存每个 SKU 的当前总量和预占量, 具体变更历史在
inventory_transactions. 数据库约束保证预占量不会超过总量.
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Inventory(Base):
    """一个 SKU 的当前库存快照, 不承担流水审计职责."""

    __tablename__ = "inventory"

    # 一个 SKU 只能有一行库存; 三个检查约束防止数量出现非法状态.
    __table_args__ = (
        UniqueConstraint("sku_id", name="uq_inventory_sku_id"),
        CheckConstraint(
            "total_quantity >= 0",
            name="ck_inventory_total_non_negative",
        ),
        CheckConstraint(
            "reserved_quantity >= 0",
            name="ck_inventory_reserved_non_negative",
        ),
        CheckConstraint(
            "reserved_quantity <= total_quantity",
            name="ck_inventory_reserved_le_total",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    # 库存挂在 SKU 维度, 与下单和库存操作的最小单位保持一致.
    sku_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "skus.id",
            name="fk_inventory_sku",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        nullable=False,
    )

    # 物理总库存, 包括已被订单预占的部分.
    total_quantity: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        server_default=text("0"),
    )

    # 已预占但尚未出库的数量; 可用库存 = total_quantity - reserved_quantity.
    reserved_quantity: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        server_default=text("0"),
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
