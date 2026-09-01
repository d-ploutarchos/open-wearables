"""add running efforts to the provider-neutral performance ledger

Revision ID: e8f2c73b91a4
Revises: b7e4a91c2d63
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e8f2c73b91a4"
down_revision: Union[str, None] = "b7e4a91c2d63"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("canonical_workout", sa.Column("running_pr_algorithm_version", sa.String(length=32), nullable=True))
    op.create_table(
        "running_effort",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("canonical_workout_id", sa.UUID(), nullable=False),
        sa.Column("event_record_id", sa.UUID(), nullable=False),
        sa.Column("performed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("target_distance_meters", sa.Integer(), nullable=False),
        sa.Column("actual_distance_meters", sa.Numeric(12, 3), nullable=False),
        sa.Column("elapsed_seconds", sa.Numeric(12, 3), nullable=False),
        sa.Column("pace_seconds_per_km", sa.Numeric(10, 3), nullable=False),
        sa.Column("calculation_method", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.String(length=32), nullable=False),
        sa.Column("algorithm_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["canonical_workout_id"], ["canonical_workout.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["event_record_id"], ["event_record.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_running_effort_workout_distance_algorithm",
        "running_effort",
        ["canonical_workout_id", "target_distance_meters", "algorithm_version"],
        unique=True,
    )
    op.create_index(
        "ix_running_effort_user_distance_performed",
        "running_effort",
        ["user_id", "target_distance_meters", "performed_at"],
    )
    op.add_column("performance_record", sa.Column("distance_meters", sa.Integer(), nullable=True))
    op.add_column("performance_record", sa.Column("running_effort_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_performance_record_running_effort_id_running_effort",
        "performance_record",
        "running_effort",
        ["running_effort_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column("performance_record_history", sa.Column("running_effort_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_performance_record_history_running_effort_id_running_effort",
        "performance_record_history",
        "running_effort",
        ["running_effort_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_performance_record_history_running_effort_id_running_effort",
        "performance_record_history",
        type_="foreignkey",
    )
    op.drop_column("performance_record_history", "running_effort_id")
    op.drop_constraint(
        "fk_performance_record_running_effort_id_running_effort",
        "performance_record",
        type_="foreignkey",
    )
    op.drop_column("performance_record", "running_effort_id")
    op.drop_column("performance_record", "distance_meters")
    op.drop_index("ix_running_effort_user_distance_performed", table_name="running_effort")
    op.drop_index("uq_running_effort_workout_distance_algorithm", table_name="running_effort")
    op.drop_table("running_effort")
    op.drop_column("canonical_workout", "running_pr_algorithm_version")
