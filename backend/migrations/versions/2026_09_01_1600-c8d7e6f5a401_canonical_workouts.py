"""add canonical workouts and provider source links

Revision ID: c8d7e6f5a401
Revises: f2b6d4a8c901
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c8d7e6f5a401"
down_revision: Union[str, None] = "f2b6d4a8c901"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "canonical_workout",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("fingerprint", sa.String(length=100), nullable=False),
        sa.Column("workout_type", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("start_datetime", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_datetime", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_canonical_workout_user_fingerprint",
        "canonical_workout",
        ["user_id", "fingerprint"],
        unique=True,
    )
    op.create_index(
        "ix_canonical_workout_user_start",
        "canonical_workout",
        ["user_id", "start_datetime"],
    )
    op.create_table(
        "canonical_workout_source",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("canonical_workout_id", sa.UUID(), nullable=False),
        sa.Column("event_record_id", sa.UUID(), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["canonical_workout_id"], ["canonical_workout.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["event_record_id"], ["event_record.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_canonical_workout_source_record",
        "canonical_workout_source",
        ["event_record_id"],
        unique=True,
    )
    op.create_index(
        "ix_canonical_workout_source_canonical",
        "canonical_workout_source",
        ["canonical_workout_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_canonical_workout_source_canonical", table_name="canonical_workout_source")
    op.drop_index("uq_canonical_workout_source_record", table_name="canonical_workout_source")
    op.drop_table("canonical_workout_source")
    op.drop_index("ix_canonical_workout_user_start", table_name="canonical_workout")
    op.drop_index("uq_canonical_workout_user_fingerprint", table_name="canonical_workout")
    op.drop_table("canonical_workout")
