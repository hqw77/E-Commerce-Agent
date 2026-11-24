"""商品 SPU 模型.

products 表示商品主数据, 具体规格和价格由 skus 承担.
商品状态和 published_at/archived_at 必须成对满足约束, 防止出现
已上架但无发布时间等不一致状态.
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.category import Category
    from app.models.sku import Sku


class Product(Base):
    """商品 SPU, 是 SKU 的聚合根."""

    __tablename__ = "products"

    # product_no 是外部可展示编号, 生命周期状态由 CheckConstraint 强制校验.
    __table_args__ = (
        UniqueConstraint(
            "product_no",
            name="uq_products_product_no",
        ),
        Index("ix_products_category_id", "category_id"),
        Index("ix_products_status_category", "status", "category_id"),
        CheckConstraint(
            "status IN ('DRAFT', 'ACTIVE', 'INACTIVE', 'ARCHIVED')",
            name="ck_products_status",
        ),
        CheckConstraint(
            "(status = 'DRAFT' AND published_at IS NULL "
            "AND archived_at IS NULL) OR "
            "(status = 'ACTIVE' AND published_at IS NOT NULL "
            "AND archived_at IS NULL) OR "
            "(status = 'INACTIVE' AND published_at IS NOT NULL "
            "AND archived_at IS NULL) OR "
            "(status = 'ARCHIVED' AND archived_at IS NOT NULL)",
            name="ck_products_lifecycle",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    # 使用 ascii_bin 保证编号大小写敏感且不受排序规则影响.
    product_no: Mapped[str] = mapped_column(
        mysql.VARCHAR(32, charset="ascii", collation="ascii_bin"),
        nullable=False,
    )

    # 商品必须归属分类; RESTRICT 防止误删仍被商品引用的分类.
    category_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "categories.id",
            name="fk_products_category",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        nullable=False,
    )

    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # DRAFT/ACTIVE/INACTIVE/ARCHIVED 与时间字段由数据库约束联合保证.
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default="DRAFT",
    )

    # 首次上架时间, DRAFT 必须为空, ACTIVE/INACTIVE 必须有值.
    published_at: Mapped[datetime | None] = mapped_column(
        mysql.DATETIME(fsp=6),
        nullable=True,
    )

    # 归档时间, 只有 ARCHIVED 状态允许非空.
    archived_at: Mapped[datetime | None] = mapped_column(
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

    # 商品与分类多对一; SKU 与商品一对多.
    category: Mapped["Category"] = relationship(
        back_populates="products",
    )

    skus: Mapped[list["Sku"]] = relationship(
        back_populates="product",
    )
