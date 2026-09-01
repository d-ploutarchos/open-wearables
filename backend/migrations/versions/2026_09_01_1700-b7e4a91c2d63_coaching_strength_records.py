"""add strength efforts and performance record ledger

Revision ID: b7e4a91c2d63
Revises: c8d7e6f5a401
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b7e4a91c2d63"
down_revision: Union[str, None] = "c8d7e6f5a401"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "strength_effort",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("canonical_workout_id", sa.UUID(), nullable=False),
        sa.Column("event_record_id", sa.UUID(), nullable=False),
        sa.Column("exercise_definition_id", sa.UUID(), nullable=False),
        sa.Column("exercise_set_id", sa.UUID(), nullable=False),
        sa.Column("performed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("set_type", sa.String(length=32), nullable=False),
        sa.Column("repetitions", sa.Integer(), nullable=False),
        sa.Column("load_kg", sa.Numeric(10, 3), nullable=False),
        sa.Column("volume_kg", sa.Numeric(12, 3), nullable=False),
        sa.Column("estimated_one_rep_max_kg", sa.Numeric(10, 3), nullable=True),
        sa.Column("algorithm_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["canonical_workout_id"], ["canonical_workout.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["event_record_id"], ["event_record.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["exercise_definition_id"], ["exercise_definition.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["exercise_set_id"], ["exercise_set.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_strength_effort_set_algorithm",
        "strength_effort",
        ["exercise_set_id", "algorithm_version"],
        unique=True,
    )
    op.create_index(
        "ix_strength_effort_user_exercise_performed",
        "strength_effort",
        ["user_id", "exercise_definition_id", "performed_at"],
    )
    op.create_index(
        "ix_strength_effort_canonical_workout",
        "strength_effort",
        ["canonical_workout_id"],
    )

    op.create_table(
        "performance_record",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("sport", sa.String(length=32), nullable=False),
        sa.Column("record_type", sa.String(length=32), nullable=False),
        sa.Column("scope_key", sa.String(length=255), nullable=False),
        sa.Column("exercise_definition_id", sa.UUID(), nullable=True),
        sa.Column("repetition_count", sa.Integer(), nullable=True),
        sa.Column("value", sa.Numeric(12, 3), nullable=False),
        sa.Column("unit", sa.String(length=32), nullable=False),
        sa.Column("strength_effort_id", sa.UUID(), nullable=True),
        sa.Column("canonical_workout_id", sa.UUID(), nullable=False),
        sa.Column("achieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("algorithm_version", sa.String(length=32), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["exercise_definition_id"], ["exercise_definition.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["strength_effort_id"], ["strength_effort.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["canonical_workout_id"], ["canonical_workout.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_performance_record_scope",
        "performance_record",
        ["user_id", "sport", "record_type", "scope_key"],
        unique=True,
    )
    op.create_index("ix_performance_record_user_sport", "performance_record", ["user_id", "sport"])

    op.create_table(
        "performance_record_history",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("performance_record_id", sa.UUID(), nullable=False),
        sa.Column("strength_effort_id", sa.UUID(), nullable=True),
        sa.Column("canonical_workout_id", sa.UUID(), nullable=False),
        sa.Column("value", sa.Numeric(12, 3), nullable=False),
        sa.Column("previous_value", sa.Numeric(12, 3), nullable=True),
        sa.Column("achieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("algorithm_version", sa.String(length=32), nullable=False),
        sa.Column("change_type", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["performance_record_id"], ["performance_record.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["strength_effort_id"], ["strength_effort.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["canonical_workout_id"], ["canonical_workout.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_performance_record_history_record_achieved",
        "performance_record_history",
        ["performance_record_id", "achieved_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_performance_record_history_record_achieved", table_name="performance_record_history")
    op.drop_table("performance_record_history")
    op.drop_index("ix_performance_record_user_sport", table_name="performance_record")
    op.drop_index("uq_performance_record_scope", table_name="performance_record")
    op.drop_table("performance_record")
    op.drop_index("ix_strength_effort_canonical_workout", table_name="strength_effort")
    op.drop_index("ix_strength_effort_user_exercise_performed", table_name="strength_effort")
    op.drop_index("uq_strength_effort_set_algorithm", table_name="strength_effort")
    op.drop_table("strength_effort")
