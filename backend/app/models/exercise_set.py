from decimal import Decimal
from uuid import UUID

from sqlalchemy import ForeignKey, Index, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.database import BaseDbModel
from app.mappings import PrimaryKey, numeric_10_3, str_32


class ExerciseSet(BaseDbModel):
    """A queryable set performed for one workout exercise."""

    __tablename__ = "exercise_set"
    __table_args__ = (Index("uq_exercise_set_exercise_index", "workout_exercise_id", "set_index", unique=True),)

    id: Mapped[PrimaryKey[UUID]]
    workout_exercise_id: Mapped[UUID] = mapped_column(ForeignKey("workout_exercise.id", ondelete="CASCADE"))
    set_index: Mapped[int]
    set_type: Mapped[str_32]
    weight_kg: Mapped[numeric_10_3 | None]
    reps: Mapped[int | None]
    distance_meters: Mapped[numeric_10_3 | None]
    duration_seconds: Mapped[int | None]
    rpe: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))
    custom_metric: Mapped[numeric_10_3 | None]
