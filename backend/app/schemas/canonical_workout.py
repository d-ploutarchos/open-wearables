from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class CanonicalWorkoutSourceResponse(BaseModel):
    event_record_id: UUID
    provider: str
    device: str | None = None
    start_time: datetime
    end_time: datetime


class CanonicalWorkoutResponse(BaseModel):
    id: UUID
    user_id: UUID
    type: str
    name: str
    start_time: datetime
    end_time: datetime
    duration_seconds: int
    calories_kcal: float | None = None
    distance_meters: float | None = None
    avg_heart_rate_bpm: int | None = None
    max_heart_rate_bpm: int | None = None
    exercises: list[dict[str, Any]] | None = None
    sources: list[CanonicalWorkoutSourceResponse]
    provenance: dict[str, str]
