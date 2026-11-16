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
    """Stock keeping unit belonging to one SPU."""

    __tablename__ = "skus"

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

    attributes: Mapped[dict[str, str]] = mapped_column(
        JSON,
        nullable=False,
    )

    attributes_hash: Mapped[str] = mapped_column(
        mysql.CHAR(64, charset="ascii", collation="ascii_bin"),
        nullable=False,
    )

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

    product: Mapped["Product"] = relationship(
        back_populates="skus",
    )
