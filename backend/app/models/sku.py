"""SKU 模型.

SKU 是下单, 定价和库存管理的最小单位. 同一 SPU 下通过 attributes_hash
保证规格组合唯一, 避免相同规格被重复创建.
"""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
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
    from app.models.product import Product


class Sku(Base):
    """商品规格单元, 归属一个 SPU."""

    __tablename__ = "skus"

    # sku_code 对外唯一; product_id + attributes_hash 保证规格组合唯一.
    __table_args__ = (
        UniqueConstraint("sku_code", name="uq_skus_sku_code"),
        UniqueConstraint(
            "product_id",
            "attributes_hash",
            name="uq_skus_product_attributes",
        ),
        Index("ix_skus_product_status", "product_id", "status"),
        CheckConstraint("price > 0", name="ck_skus_price"),
        CheckConstraint(
            "status IN ('ACTIVE', 'INACTIVE')",
            name="ck_skus_status",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    # RESTRICT 防止删除仍有 SKU 的商品.
    product_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "products.id",
            name="fk_skus_product",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        nullable=False,
    )

    sku_code: Mapped[str] = mapped_column(
        mysql.VARCHAR(64, charset="ascii", collation="ascii_bin"),
        nullable=False,
    )

    # 规格原文用于展示, 例如颜色/尺寸; 唯一性依赖 attributes_hash.
    attributes: Mapped[dict[str, str]] = mapped_column(
        JSON,
        nullable=False,
    )

    # 对规范化后的属性做 SHA-256, 让 JSON 也能参与唯一约束.
    attributes_hash: Mapped[str] = mapped_column(
        mysql.CHAR(64, charset="ascii", collation="ascii_bin"),
        nullable=False,
    )

    # 下单时会把该价格快照到 order_items, 后续调价不影响历史订单.
    price: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default="ACTIVE",
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

    # 反向归属关系, 不负责级联删除.
    product: Mapped["Product"] = relationship(
        back_populates="skus",
    )
