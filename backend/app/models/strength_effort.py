from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import ForeignKey, Index, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.database import BaseDbModel
from app.mappings import FKUser, PrimaryKey, str_32


class StrengthEffort(BaseDbModel):
    """Versioned performance facts derived from one eligible strength set."""

    __tablename__ = "strength_effort"
    __table_args__ = (
        Index("uq_strength_effort_set_algorithm", "exercise_set_id", "algorithm_version", unique=True),
        Index(
            "ix_strength_effort_user_exercise_performed",
            "user_id",
            "exercise_definition_id",
            "performed_at",
        ),
        Index("ix_strength_effort_canonical_workout", "canonical_workout_id"),
    )

    id: Mapped[PrimaryKey[UUID]]
    user_id: Mapped[FKUser]
    canonical_workout_id: Mapped[UUID] = mapped_column(
        ForeignKey("canonical_workout.id", ondelete="CASCADE")
    )
    event_record_id: Mapped[UUID] = mapped_column(ForeignKey("event_record.id", ondelete="CASCADE"))
    exercise_definition_id: Mapped[UUID] = mapped_column(
        ForeignKey("exercise_definition.id", ondelete="RESTRICT")
    )
    exercise_set_id: Mapped[UUID] = mapped_column(ForeignKey("exercise_set.id", ondelete="CASCADE"))
    performed_at: Mapped[datetime]
    set_type: Mapped[str_32]
    repetitions: Mapped[int]
    load_kg: Mapped[Decimal] = mapped_column(Numeric(10, 3))
    volume_kg: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    estimated_one_rep_max_kg: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    algorithm_version: Mapped[str_32]
