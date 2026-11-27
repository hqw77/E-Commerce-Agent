"""drop legacy order payment fields

Revision ID: 5d7a27f8ba5c
Revises: 80b9bbf33d5a
Create Date: 2026-11-27 18:43:45.977961

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = '5d7a27f8ba5c'
down_revision: str | Sequence[str] | None = '80b9bbf33d5a'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # 支付字段被两个 CHECK 约束引用, 必须先删约束再删列.
    op.drop_constraint(
        op.f('ck_orders_paid_amount'),
        'orders',
        type_='check',
    )
    op.drop_constraint(
        op.f('ck_orders_refunded_amount'),
        'orders',
        type_='check',
    )
    op.drop_index(op.f('ix_orders_status_expires'), table_name='orders')
    op.drop_column('orders', 'payment_status')
    op.drop_column('orders', 'refunded_amount')
    op.drop_column('orders', 'paid_amount')
    op.drop_column('orders', 'expires_at')
    op.drop_column('orders', 'paid_at')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column('orders', sa.Column('paid_at', mysql.DATETIME(fsp=6), nullable=True))
    op.add_column(
        'orders',
        sa.Column(
            'expires_at',
            mysql.DATETIME(fsp=6),
            nullable=False,
            server_default=sa.text('CURRENT_TIMESTAMP(6)'),
        ),
    )
    op.add_column('orders', sa.Column('paid_amount', mysql.DECIMAL(precision=12, scale=2), server_default=sa.text('(0.00)'), nullable=False))
    op.add_column('orders', sa.Column('refunded_amount', mysql.DECIMAL(precision=12, scale=2), server_default=sa.text('(0.00)'), nullable=False))
    op.add_column('orders', sa.Column('payment_status', mysql.VARCHAR(length=24), server_default=sa.text("'UNPAID'"), nullable=False))
    op.create_check_constraint(
        op.f('ck_orders_paid_amount'),
        'orders',
        'paid_amount >= 0 AND paid_amount <= total_amount',
    )
    op.create_check_constraint(
        op.f('ck_orders_refunded_amount'),
        'orders',
        'refunded_amount >= 0 AND refunded_amount <= paid_amount',
    )
    op.create_index(op.f('ix_orders_status_expires'), 'orders', ['status', 'expires_at'], unique=False)
