from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Index, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.database import BaseDbModel
from app.mappings import FKUser, PrimaryKey, str_32, str_255


class PerformanceRecord(BaseDbModel):
    """The current best athletic performance for one user-scoped metric."""

    __tablename__ = "performance_record"
    __table_args__ = (
        Index("uq_performance_record_scope", "user_id", "sport", "record_type", "scope_key", unique=True),
        Index("ix_performance_record_user_sport", "user_id", "sport"),
    )

    id: Mapped[PrimaryKey[UUID]]
    user_id: Mapped[FKUser]
    sport: Mapped[str_32]
    record_type: Mapped[str_32]
    scope_key: Mapped[str_255]
    exercise_definition_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("exercise_definition.id", ondelete="SET NULL")
    )
    repetition_count: Mapped[int | None]
    value: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    unit: Mapped[str_32]
    strength_effort_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("strength_effort.id", ondelete="SET NULL")
    )
    canonical_workout_id: Mapped[UUID] = mapped_column(
        ForeignKey("canonical_workout.id", ondelete="CASCADE")
    )
    achieved_at: Mapped[datetime]
    algorithm_version: Mapped[str_32]
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    updated_at: Mapped[datetime]


class PerformanceRecordHistory(BaseDbModel):
    """Append-only sequence of changes to a current performance record."""

    __tablename__ = "performance_record_history"
    __table_args__ = (
        Index("ix_performance_record_history_record_achieved", "performance_record_id", "achieved_at"),
    )

    id: Mapped[PrimaryKey[UUID]]
    performance_record_id: Mapped[UUID] = mapped_column(
        ForeignKey("performance_record.id", ondelete="CASCADE")
    )
    strength_effort_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("strength_effort.id", ondelete="SET NULL")
    )
    canonical_workout_id: Mapped[UUID] = mapped_column(
        ForeignKey("canonical_workout.id", ondelete="CASCADE")
    )
    value: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    previous_value: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    achieved_at: Mapped[datetime]
    algorithm_version: Mapped[str_32]
    change_type: Mapped[str_32]
