"""add product image url

Revision ID: 6f3b2c1d4e5a
Revises: b96d3aae8b3d
Create Date: 2026-11-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "6f3b2c1d4e5a"
down_revision: str | Sequence[str] | None = "b96d3aae8b3d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column("image_url", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("products", "image_url")
