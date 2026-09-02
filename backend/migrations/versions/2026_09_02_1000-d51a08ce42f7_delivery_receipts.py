"""add agent delivery receipts

Revision ID: d51a08ce42f7
Revises: f4a1d82c63b7
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d51a08ce42f7"
down_revision: Union[str, None] = "f4a1d82c63b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "delivery_receipt",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("event_id", sa.String(length=255), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("stage", sa.String(length=50), nullable=False),
        sa.Column("source", sa.String(length=100), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("detail", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_delivery_receipt_user_occurred",
        "delivery_receipt",
        ["user_id", "occurred_at"],
        unique=False,
    )
    op.create_index(
        "uq_delivery_receipt_event_stage",
        "delivery_receipt",
        ["user_id", "event_id", "stage"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_delivery_receipt_event_stage", table_name="delivery_receipt")
    op.drop_index("ix_delivery_receipt_user_occurred", table_name="delivery_receipt")
    op.drop_table("delivery_receipt")
