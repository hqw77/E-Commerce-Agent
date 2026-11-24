"""商品分类模型.

categories 通过 parent_id 自关联形成分类树. 商品必须归属一个分类,
因此删除分类时不能直接级联删除商品.
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    text,
)
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.product import Product


class Category(Base):
    """商品分类树节点, 支持根分类和子分类."""

    __tablename__ = "categories"

    # parent_id 与 sort_order 的组合索引用于按父分类稳定排序读取.
    __table_args__ = (
        Index("ix_categories_parent_sort", "parent_id", "sort_order"),
        CheckConstraint(
            "status IN ('ENABLED', 'DISABLED')",
            name="ck_categories_status",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    # NULL 表示根分类; 自关联外键禁止删除仍被引用的父分类.
    parent_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "categories.id",
            name="fk_categories_parent",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        nullable=True,
    )

    # 分类名称只用于展示, 唯一性由服务层按业务规则决定.
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    # 同一父分类下按该值升序展示, 不依赖主键顺序.
    sort_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )

    # 只有 ENABLED 的分类才允许继续被商品使用.
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default="ENABLED",
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

    # 反向关系便于查询某分类下的商品, 不控制级联删除.
    products: Mapped[list["Product"]] = relationship(
        back_populates="category",
    )
