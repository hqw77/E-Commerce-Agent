"""widen inventory transaction type

Revision ID: 5f14d68fcbd1
Revises: 22a36fc5af9c
Create Date: 2026-11-14 01:00:53.868698

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5f14d68fcbd1"
down_revision: str | Sequence[str] | None = "22a36fc5af9c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Allow the reserved-outbound ledger type."""
    op.alter_column(
        "inventory_transactions",
        "transaction_type",
        existing_type=sa.String(length=16),
        type_=sa.String(length=24),
        existing_nullable=False,
    )


def downgrade() -> None:
    """Restore the previous ledger type width."""
    op.alter_column(
        "inventory_transactions",
        "transaction_type",
        existing_type=sa.String(length=24),
        type_=sa.String(length=16),
        existing_nullable=False,
    )
