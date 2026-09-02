"""add user scoped agent credentials

Revision ID: a62b93fd71c8
Revises: d51a08ce42f7
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a62b93fd71c8"
down_revision: Union[str, None] = "d51a08ce42f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_credential",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("token_prefix", sa.String(length=32), nullable=False),
        sa.Column("webhook_endpoint_id", sa.String(length=64), nullable=True),
        sa.Column("webhook_url", sa.Text(), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_agent_credential_user_active",
        "agent_credential",
        ["user_id", "revoked_at"],
        unique=False,
    )
    op.create_index(
        "uq_agent_credential_token_hash",
        "agent_credential",
        ["token_hash"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_agent_credential_token_hash", table_name="agent_credential")
    op.drop_index("ix_agent_credential_user_active", table_name="agent_credential")
    op.drop_table("agent_credential")
