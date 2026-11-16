from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
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
    from app.models.product import Product
    from app.models.sku import Sku


class OrderItem(Base):
    """Immutable snapshot of an ordered SKU."""

    __tablename__ = "order_items"

    __table_args__ = (
        UniqueConstraint(
            "order_id",
            "sku_id",
            name="uq_order_items_order_sku",
        ),
        Index("ix_order_items_sku_id", "sku_id"),
        Index("ix_order_items_product_id", "product_id"),
        CheckConstraint("quantity > 0", name="ck_order_items_quantity"),
        CheckConstraint(
            "unit_price > 0",
            name="ck_order_items_unit_price",
        ),
        CheckConstraint(
            "line_amount > 0",
            name="ck_order_items_line_amount",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    order_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "orders.id",
            name="fk_order_items_order",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        nullable=False,
    )

    product_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "products.id",
            name="fk_order_items_product",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        nullable=False,
    )

    sku_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "skus.id",
            name="fk_order_items_sku",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        nullable=False,
    )

    product_no: Mapped[str] = mapped_column(
        mysql.VARCHAR(32, charset="ascii", collation="ascii_bin"),
        nullable=False,
    )

    product_name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    sku_code: Mapped[str] = mapped_column(
        mysql.VARCHAR(64, charset="ascii", collation="ascii_bin"),
        nullable=False,
    )

    sku_attributes: Mapped[dict[str, str]] = mapped_column(
        JSON,
        nullable=False,
    )

    currency: Mapped[str] = mapped_column(
        mysql.CHAR(3),
        nullable=False,
        server_default="CNY",
    )

    unit_price: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )

    quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    line_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        mysql.DATETIME(fsp=6),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP(6)"),
    )

    order: Mapped["Order"] = relationship(
        back_populates="items",
    )

    product: Mapped["Product"] = relationship(
        foreign_keys=[product_id],
    )

    sku: Mapped["Sku"] = relationship(
        foreign_keys=[sku_id],
    )

    after_sales: Mapped[list["AfterSale"]] = relationship(
        back_populates="order_item",
    )
