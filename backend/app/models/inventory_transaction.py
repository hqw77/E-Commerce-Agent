"""库存流水模型.

inventory_transactions 是只追加的库存账本, 记录每次变更的增量, 变更后余额,
业务来源和幂等键. 库存快照与流水必须同时更新, 否则无法审计和对账.
"""

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
    """只追加的库存流水, 不允许原地修改历史记录."""

    __tablename__ = "inventory_transactions"

    # 幂等键全局唯一, 是库存操作安全重试的最后防线.
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

    # 流水归属 SKU, 与 inventory 的快照维度一致.
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

    # INITIAL/STOCK_IN/RESERVE/RELEASE/RESERVED_OUTBOUND 等操作类型.
    transaction_type: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
    )

    # 本次操作对总库存的增量, 预占/释放在这里通常为 0.
    total_delta: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    # 本次操作对预占库存的增量, 用于还原当时的变化方向.
    reserved_delta: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    # 操作后的余额快照, 便于审计时不依赖重放全部历史.
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

    # 业务来源, 例如 MANUAL/ORDER/INITIAL, 用于追溯操作上下文.
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
