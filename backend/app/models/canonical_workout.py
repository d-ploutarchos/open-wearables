from datetime import datetime
from uuid import UUID

from sqlalchemy import Index
from sqlalchemy.orm import Mapped

from app.database import BaseDbModel
from app.mappings import FKUser, PrimaryKey, str_32, str_64, str_100


class CanonicalWorkout(BaseDbModel):
    """One physical workout assembled from one or more provider records."""

    __tablename__ = "canonical_workout"
    __table_args__ = (
        Index("uq_canonical_workout_user_fingerprint", "user_id", "fingerprint", unique=True),
        Index("ix_canonical_workout_user_start", "user_id", "start_datetime"),
    )

    id: Mapped[PrimaryKey[UUID]]
    user_id: Mapped[FKUser]
    fingerprint: Mapped[str_100]
    workout_type: Mapped[str_32]
    name: Mapped[str_64]
    start_datetime: Mapped[datetime]
    end_datetime: Mapped[datetime]
    updated_at: Mapped[datetime]
