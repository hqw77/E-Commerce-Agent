
"""create refresh sessions table

Revision ID: 08b7848e6368
Revises: 7bf01171c77c
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "08b7848e6368"
down_revision: Union[str, Sequence[str], None] = "7bf01171c77c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "refresh_sessions",
        sa.Column(
            "id",
            sa.BigInteger(),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("family_id", sa.String(length=36), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("replaced_by_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["replaced_by_id"],
            ["refresh_sessions.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )

    op.create_index(
        "ix_refresh_sessions_user_id",
        "refresh_sessions",
        ["user_id"],
    )
    op.create_index(
        "ix_refresh_sessions_family_id",
        "refresh_sessions",
        ["family_id"],
    )
    op.create_index(
        "ix_refresh_sessions_expires_at",
        "refresh_sessions",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_refresh_sessions_expires_at",
        table_name="refresh_sessions",
    )
    op.drop_index(
        "ix_refresh_sessions_family_id",
        table_name="refresh_sessions",
    )
    op.drop_index(
        "ix_refresh_sessions_user_id",
        table_name="refresh_sessions",
    )
    op.drop_table("refresh_sessions")
