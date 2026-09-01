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
    distance_meters: int | None = None
    value: Decimal
    unit: str
    achieved_at: datetime
    canonical_workout_id: UUID
    source_effort_id: UUID | None = None
    source_running_effort_id: UUID | None = None
    source_load_kg: Decimal | None = None
    source_repetitions: int | None = None
    source_duration_seconds: Decimal | None = None
    source_distance_meters: Decimal | None = None
    segment_start_datetime: datetime | None = None
    segment_end_datetime: datetime | None = None
    calculation_method: str | None = None
    confidence: str | None = None
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
    distance_meters: int | None = None
    value: Decimal
    previous_value: Decimal | None = None
    unit: str
    achieved_at: datetime
    canonical_workout_id: UUID
    source_effort_id: UUID | None = None
    source_running_effort_id: UUID | None = None
    algorithm_version: str
    change_type: str


class PerformanceRecordChangeResponse(PerformanceRecordResponse):
    change_type: str
    previous_value: Decimal | None = None


class StrengthAnalysisResult(BaseModel):
    canonical_workout_id: UUID
    efforts_processed: int
    records_changed: list[PerformanceRecordChangeResponse]


class RunningAnalysisResult(BaseModel):
    canonical_workout_id: UUID
    efforts_processed: int
    records_changed: list[PerformanceRecordChangeResponse]


class StrengthProgressInsight(BaseModel):
    exercise_id: UUID
    exercise_name: str
    status: str
    sessions: int
    sessions_in_window: int
    latest_performed_at: datetime
    latest_estimated_one_rep_max_kg: Decimal
    personal_best_estimated_one_rep_max_kg: Decimal
    personal_best_at: datetime
    estimated_one_rep_max_change_from_first_kg: Decimal
    estimated_one_rep_max_change_percent: Decimal | None = None
    sessions_since_best: int
    days_since_best: int
    latest_top_load_kg: Decimal
    latest_volume_kg: Decimal
    recent_average_volume_kg: Decimal | None = None
    previous_average_volume_kg: Decimal | None = None
    volume_change_percent: Decimal | None = None


class RunningProgressInsight(BaseModel):
    distance_meters: int
    status: str
    attempts: int
    attempts_in_window: int
    latest_performed_at: datetime
    latest_time_seconds: Decimal
    personal_best_time_seconds: Decimal
    personal_best_at: datetime
    seconds_improved_from_first: Decimal
    improvement_percent: Decimal | None = None
    attempts_since_best: int
    days_since_best: int
    calculation_method: str
    confidence: str


class CoachingProgressResponse(BaseModel):
    user_id: UUID
    generated_at: datetime
    window_days: int
    plateau_attempts: int
    strength: list[StrengthProgressInsight]
    running: list[RunningProgressInsight]
