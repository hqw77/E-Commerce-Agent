"""drop legacy payment and refund tables

Revision ID: 80b9bbf33d5a
Revises: b7c8d9e0f1a2
Create Date: 2026-11-27 02:08:40.536274

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = '80b9bbf33d5a'
down_revision: str | Sequence[str] | None = 'b7c8d9e0f1a2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Remove the retired payment/refund domain.

    refunds must be dropped before payments because it owns the FK to payments.
    """
    op.drop_table('refunds')
    op.drop_table('payments')


def downgrade() -> None:
    """Recreate the legacy tables in FK-safe order."""
    op.create_table(
        'payments',
        sa.Column('id', mysql.BIGINT(), autoincrement=True, nullable=False),
        sa.Column('payment_no', mysql.VARCHAR(charset='ascii', collation='ascii_bin', length=32), nullable=False),
        sa.Column('order_id', mysql.BIGINT(), autoincrement=False, nullable=False),
        sa.Column('user_id', mysql.BIGINT(), autoincrement=False, nullable=False),
        sa.Column('channel', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=16), nullable=False),
        sa.Column('amount', mysql.DECIMAL(precision=12, scale=2), nullable=False),
        sa.Column('status', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=24), server_default=sa.text("'PENDING'"), nullable=False),
        sa.Column('provider_trade_no', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=64), nullable=True),
        sa.Column('refunded_amount', mysql.DECIMAL(precision=12, scale=2), server_default=sa.text('(0.00)'), nullable=False),
        sa.Column('exception_reason', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=64), nullable=True),
        sa.Column('failure_code', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=64), nullable=True),
        sa.Column('failure_message', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=255), nullable=True),
        sa.Column('paid_at', mysql.DATETIME(fsp=6), nullable=True),
        sa.Column('closed_at', mysql.DATETIME(fsp=6), nullable=True),
        sa.Column('created_at', mysql.DATETIME(fsp=6), server_default=sa.text('CURRENT_TIMESTAMP(6)'), nullable=False),
        sa.Column('updated_at', mysql.DATETIME(fsp=6), server_default=sa.text('CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)'), nullable=False),
        sa.CheckConstraint('((`refunded_amount` >= 0) and (`refunded_amount` <= `amount`))', name=op.f('ck_payments_refunded_amount')),
        sa.CheckConstraint('(`amount` > 0)', name=op.f('ck_payments_amount')),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], name=op.f('fk_payments_order'), onupdate='RESTRICT', ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_payments_user'), onupdate='RESTRICT', ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        mysql_collate='utf8mb4_unicode_ci',
        mysql_default_charset='utf8mb4',
        mysql_engine='InnoDB',
    )
    op.create_index(op.f('uq_payments_payment_no'), 'payments', ['payment_no'], unique=True)
    op.create_index(op.f('uq_payments_order_id'), 'payments', ['order_id'], unique=True)
    op.create_index(op.f('uq_payments_channel_trade_no'), 'payments', ['channel', 'provider_trade_no'], unique=True)
    op.create_index(op.f('ix_payments_status_created'), 'payments', ['status', 'created_at'], unique=False)
    op.create_index(op.f('ix_payments_order_status'), 'payments', ['order_id', 'status'], unique=False)

    op.create_table(
        'refunds',
        sa.Column('id', mysql.BIGINT(), autoincrement=True, nullable=False),
        sa.Column('refund_no', mysql.VARCHAR(charset='ascii', collation='ascii_bin', length=32), nullable=False),
        sa.Column('order_id', mysql.BIGINT(), autoincrement=False, nullable=False),
        sa.Column('payment_id', mysql.BIGINT(), autoincrement=False, nullable=False),
        sa.Column('after_sales_id', mysql.BIGINT(), autoincrement=False, nullable=True),
        sa.Column('user_id', mysql.BIGINT(), autoincrement=False, nullable=False),
        sa.Column('amount', mysql.DECIMAL(precision=12, scale=2), nullable=False),
        sa.Column('reason', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=255), nullable=False),
        sa.Column('channel', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=16), nullable=False),
        sa.Column('status', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=24), server_default=sa.text("'PENDING'"), nullable=False),
        sa.Column('provider_refund_no', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=64), nullable=True),
        sa.Column('idempotency_key', mysql.VARCHAR(charset='ascii', collation='ascii_bin', length=128), nullable=False),
        sa.Column('failure_code', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=64), nullable=True),
        sa.Column('failure_message', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=255), nullable=True),
        sa.Column('requested_at', mysql.DATETIME(fsp=6), server_default=sa.text('CURRENT_TIMESTAMP(6)'), nullable=False),
        sa.Column('processed_at', mysql.DATETIME(fsp=6), nullable=True),
        sa.Column('created_at', mysql.DATETIME(fsp=6), server_default=sa.text('CURRENT_TIMESTAMP(6)'), nullable=False),
        sa.Column('updated_at', mysql.DATETIME(fsp=6), server_default=sa.text('CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)'), nullable=False),
        sa.CheckConstraint('(`amount` > 0)', name=op.f('ck_refunds_amount')),
        sa.ForeignKeyConstraint(['after_sales_id'], ['after_sales.id'], name=op.f('fk_refunds_after_sales'), onupdate='RESTRICT', ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], name=op.f('fk_refunds_order'), onupdate='RESTRICT', ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['payment_id'], ['payments.id'], name=op.f('fk_refunds_payment'), onupdate='RESTRICT', ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_refunds_user'), onupdate='RESTRICT', ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        mysql_collate='utf8mb4_unicode_ci',
        mysql_default_charset='utf8mb4',
        mysql_engine='InnoDB',
    )
    op.create_index(op.f('uq_refunds_refund_no'), 'refunds', ['refund_no'], unique=True)
    op.create_index(op.f('uq_refunds_payment_idempotency'), 'refunds', ['payment_id', 'idempotency_key'], unique=True)
    op.create_index(op.f('uq_refunds_after_sales_id'), 'refunds', ['after_sales_id'], unique=True)
    op.create_index(op.f('ix_refunds_payment_status'), 'refunds', ['payment_id', 'status'], unique=False)
    op.create_index(op.f('ix_refunds_order_status'), 'refunds', ['order_id', 'status'], unique=False)
