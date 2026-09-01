"""add Hevy connection state and normalized strength training tables

Revision ID: f2b6d4a8c901
Revises: a4c9e8071d52
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f2b6d4a8c901"
down_revision: Union[str, None] = "a4c9e8071d52"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("user_connection", sa.Column("webhook_secret_hash", sa.Text(), nullable=True))
    op.add_column("user_connection", sa.Column("last_webhook_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "exercise_definition",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("provider_exercise_id", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("normalized_name", sa.String(length=255), nullable=False),
        sa.Column("equipment", sa.String(length=64), nullable=True),
        sa.Column("primary_muscle_group", sa.String(length=64), nullable=True),
        sa.Column("is_custom", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_exercise_definition_provider_identity",
        "exercise_definition",
        ["user_id", "provider", "provider_exercise_id"],
        unique=True,
    )
    op.create_index(
        "ix_exercise_definition_user_normalized_name",
        "exercise_definition",
        ["user_id", "normalized_name"],
    )

    op.create_table(
        "workout_exercise",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("record_id", sa.UUID(), nullable=False),
        sa.Column("exercise_definition_id", sa.UUID(), nullable=False),
        sa.Column("exercise_index", sa.Integer(), nullable=False),
        sa.Column("title_at_time", sa.String(length=255), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("superset_id", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["record_id"], ["event_record.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["exercise_definition_id"],
            ["exercise_definition.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_workout_exercise_record_index",
        "workout_exercise",
        ["record_id", "exercise_index"],
        unique=True,
    )
    op.create_index(
        "ix_workout_exercise_definition_record",
        "workout_exercise",
        ["exercise_definition_id", "record_id"],
    )

    op.create_table(
        "exercise_set",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("workout_exercise_id", sa.UUID(), nullable=False),
        sa.Column("set_index", sa.Integer(), nullable=False),
        sa.Column("set_type", sa.String(length=32), nullable=False),
        sa.Column("weight_kg", sa.Numeric(precision=10, scale=3), nullable=True),
        sa.Column("reps", sa.Integer(), nullable=True),
        sa.Column("distance_meters", sa.Numeric(precision=10, scale=3), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("rpe", sa.Numeric(precision=4, scale=2), nullable=True),
        sa.Column("custom_metric", sa.Numeric(precision=10, scale=3), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["workout_exercise_id"], ["workout_exercise.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_exercise_set_exercise_index",
        "exercise_set",
        ["workout_exercise_id", "set_index"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_exercise_set_exercise_index", table_name="exercise_set")
    op.drop_table("exercise_set")
    op.drop_index("ix_workout_exercise_definition_record", table_name="workout_exercise")
    op.drop_index("uq_workout_exercise_record_index", table_name="workout_exercise")
    op.drop_table("workout_exercise")
    op.drop_index("ix_exercise_definition_user_normalized_name", table_name="exercise_definition")
    op.drop_index("uq_exercise_definition_provider_identity", table_name="exercise_definition")
    op.drop_table("exercise_definition")
    op.drop_column("user_connection", "last_webhook_at")
    op.drop_column("user_connection", "webhook_secret_hash")
