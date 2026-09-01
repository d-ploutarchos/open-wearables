from uuid import UUID

from sqlalchemy import ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.database import BaseDbModel
from app.mappings import PrimaryKey, str_50


class CanonicalWorkoutSource(BaseDbModel):
    """Links a provider-specific event record to its physical workout."""

    __tablename__ = "canonical_workout_source"
    __table_args__ = (
        Index("uq_canonical_workout_source_record", "event_record_id", unique=True),
        Index("ix_canonical_workout_source_canonical", "canonical_workout_id"),
    )

    id: Mapped[PrimaryKey[UUID]]
    canonical_workout_id: Mapped[UUID] = mapped_column(
        ForeignKey("canonical_workout.id", ondelete="CASCADE")
    )
    event_record_id: Mapped[UUID] = mapped_column(ForeignKey("event_record.id", ondelete="CASCADE"))
    provider: Mapped[str_50]
