from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel


class PerformanceRecordResponse(BaseModel):
    id: UUID
    sport: str
    record_type: str
    scope_key: str
    exercise_id: UUID | None = None
    exercise_name: str | None = None
    repetition_count: int | None = None
    value: Decimal
    unit: str
    achieved_at: datetime
    canonical_workout_id: UUID
    source_effort_id: UUID | None = None
    source_load_kg: Decimal | None = None
    source_repetitions: int | None = None
    algorithm_version: str
    is_active: bool


class PerformanceRecordHistoryResponse(BaseModel):
    id: UUID
    performance_record_id: UUID
    sport: str
    record_type: str
    scope_key: str
    exercise_id: UUID | None = None
    exercise_name: str | None = None
    repetition_count: int | None = None
    value: Decimal
    previous_value: Decimal | None = None
    unit: str
    achieved_at: datetime
    canonical_workout_id: UUID
    source_effort_id: UUID | None = None
    algorithm_version: str
    change_type: str


class PerformanceRecordChangeResponse(PerformanceRecordResponse):
    change_type: str
    previous_value: Decimal | None = None


class StrengthAnalysisResult(BaseModel):
    canonical_workout_id: UUID
    efforts_processed: int
    records_changed: list[PerformanceRecordChangeResponse]
