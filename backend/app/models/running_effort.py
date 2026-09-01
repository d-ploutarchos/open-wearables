from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import ForeignKey, Index, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.database import BaseDbModel
from app.mappings import FKUser, PrimaryKey, str_32


class RunningEffort(BaseDbModel):
    """Versioned measured performance for one standard running distance."""

    __tablename__ = "running_effort"
    __table_args__ = (
        Index(
            "uq_running_effort_workout_distance_algorithm",
            "canonical_workout_id",
            "target_distance_meters",
            "algorithm_version",
            unique=True,
        ),
        Index("ix_running_effort_user_distance_performed", "user_id", "target_distance_meters", "performed_at"),
    )

    id: Mapped[PrimaryKey[UUID]]
    user_id: Mapped[FKUser]
    canonical_workout_id: Mapped[UUID] = mapped_column(ForeignKey("canonical_workout.id", ondelete="CASCADE"))
    event_record_id: Mapped[UUID] = mapped_column(ForeignKey("event_record.id", ondelete="CASCADE"))
    performed_at: Mapped[datetime]
    target_distance_meters: Mapped[int]
    actual_distance_meters: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    elapsed_seconds: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    pace_seconds_per_km: Mapped[Decimal] = mapped_column(Numeric(10, 3))
    segment_start_datetime: Mapped[datetime | None]
    segment_end_datetime: Mapped[datetime | None]
    calculation_method: Mapped[str_32]
    confidence: Mapped[str_32]
    algorithm_version: Mapped[str_32]
