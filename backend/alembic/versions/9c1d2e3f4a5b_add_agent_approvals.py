"""add agent approvals audit table

Revision ID: 9c1d2e3f4a5b
Revises: 6f3b2c1d4e5a
Create Date: 2026-11-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9c1d2e3f4a5b"
down_revision: str | Sequence[str] | None = "6f3b2c1d4e5a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_approvals",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("approval_id", sa.String(length=64), nullable=False),
        sa.Column("requester_id", sa.BigInteger(), nullable=False),
        sa.Column("approver_id", sa.BigInteger(), nullable=True),
        sa.Column("conversation_id", sa.String(length=64), nullable=False),
        sa.Column("thread_id", sa.String(length=64), nullable=False),
        sa.Column("operation", sa.String(length=32), nullable=False),
        sa.Column("resource_no", sa.String(length=64), nullable=False),
        sa.Column("arguments", sa.JSON(), nullable=False),
        sa.Column("before_data", sa.JSON(), nullable=False),
        sa.Column("planned_data", sa.JSON(), nullable=False),
        sa.Column("action_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("executed_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["requester_id"],
            ["users.id"],
            name="fk_agent_approvals_requester",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["approver_id"],
            ["users.id"],
            name="fk_agent_approvals_approver",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("approval_id", name="uq_agent_approvals_approval_id"),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'executed', 'failed', 'expired')",
            name="ck_agent_approvals_status",
        ),
    )
    op.create_index(
        "ix_agent_approvals_requester",
        "agent_approvals",
        ["requester_id"],
    )
    op.create_index(
        "ix_agent_approvals_status_created",
        "agent_approvals",
        ["status", "created_at"],
    )
    op.create_index(
        "ix_agent_approvals_expires_at",
        "agent_approvals",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_agent_approvals_expires_at", table_name="agent_approvals")
    op.drop_index(
        "ix_agent_approvals_status_created",
        table_name="agent_approvals",
    )
    op.drop_index("ix_agent_approvals_requester", table_name="agent_approvals")
    op.drop_table("agent_approvals")
