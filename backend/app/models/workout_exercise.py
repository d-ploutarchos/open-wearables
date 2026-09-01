from uuid import UUID

from sqlalchemy import ForeignKey, Index, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import BaseDbModel
from app.mappings import OneToMany, PrimaryKey, str_100, str_255

from .exercise_set import ExerciseSet


class WorkoutExercise(BaseDbModel):
    """An exercise occurrence within one canonical workout."""

    __tablename__ = "workout_exercise"
    __table_args__ = (
        Index("uq_workout_exercise_record_index", "record_id", "exercise_index", unique=True),
        Index("ix_workout_exercise_definition_record", "exercise_definition_id", "record_id"),
    )

    id: Mapped[PrimaryKey[UUID]]
    record_id: Mapped[UUID] = mapped_column(ForeignKey("event_record.id", ondelete="CASCADE"))
    exercise_definition_id: Mapped[UUID] = mapped_column(ForeignKey("exercise_definition.id", ondelete="RESTRICT"))
    exercise_index: Mapped[int]
    title_at_time: Mapped[str_255]
    notes: Mapped[str | None] = mapped_column(Text)
    superset_id: Mapped[str_100 | None]

    sets: Mapped[OneToMany[ExerciseSet]] = relationship(
        ExerciseSet,
        cascade="all, delete-orphan",
        order_by="ExerciseSet.set_index",
    )
