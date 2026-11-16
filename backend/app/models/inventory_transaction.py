from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class InventoryTransaction(Base):
    """Append-only inventory ledger entry."""

    __tablename__ = "inventory_transactions"

    __table_args__ = (
        UniqueConstraint(
            "idempotency_key",
            name="uq_inventory_transactions_idempotency",
        ),
        Index(
            "ix_inventory_transactions_sku_id",
            "sku_id",
            "id",
        ),
        Index(
            "ix_inventory_transactions_business",
            "business_type",
            "business_id",
            "business_item_id",
        ),
        CheckConstraint(
            "transaction_type IN ("
            "'INITIAL', 'STOCK_IN', 'RESERVE', 'RELEASE', "
            "'RESERVED_OUTBOUND', 'DIRECT_OUTBOUND', 'ADJUSTMENT'"
            ")",
            name="ck_inventory_transactions_transaction_type",
        ),
        CheckConstraint(
            "total_after >= 0",
            name="ck_inventory_transactions_total_after",
        ),
        CheckConstraint(
            "reserved_after >= 0",
            name="ck_inventory_transactions_reserved_after",
        ),
        CheckConstraint(
            "reserved_after <= total_after",
            name="ck_inventory_transactions_reserved_le_total",
        ),
        CheckConstraint(
            "total_delta <> 0 OR reserved_delta <> 0",
            name="ck_inventory_transactions_delta_non_zero",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    sku_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "skus.id",
            name="fk_inventory_transactions_sku",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        nullable=False,
    )

    transaction_type: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
    )

    total_delta: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    reserved_delta: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    total_after: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    reserved_after: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    idempotency_key: Mapped[str] = mapped_column(
        mysql.VARCHAR(128, charset="ascii", collation="ascii_bin"),
        nullable=False,
    )

    business_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default="MANUAL",
    )

    business_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )

    business_item_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )

    operator_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "users.id",
            name="fk_inventory_transactions_operator",
            ondelete="SET NULL",
            onupdate="RESTRICT",
        ),
        nullable=True,
    )

    remark: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        mysql.DATETIME(fsp=6),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP(6)"),
    )
