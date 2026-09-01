from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel


class TrainingPeriodSummary(BaseModel):
    start_datetime: datetime
    end_datetime: datetime
    workouts: int
    total_duration_minutes: Decimal
    strength_sessions: int
    running_sessions: int
    other_sessions: int
    strength_work_sets: int
    strength_volume_kg: Decimal
    running_distance_km: Decimal


class LoadMetricComparison(BaseModel):
    metric: str
    unit: str
    current: Decimal
    previous: Decimal
    baseline_window_average: Decimal
    current_vs_previous_percent: Decimal | None = None
    recent_to_baseline_ratio: Decimal | None = None
    direction: str


class MuscleGroupLoad(BaseModel):
    muscle_group: str
    current_work_sets: int
    previous_work_sets: int
    current_sessions: int
    previous_sessions: int
    current_volume_kg: Decimal
    previous_volume_kg: Decimal
    volume_change_percent: Decimal | None = None


class HealthScoreContext(BaseModel):
    category: str
    current_observations: int
    previous_observations: int
    latest_value: Decimal | None = None
    latest_at: datetime | None = None
    latest_provider: str | None = None
    current_average: Decimal | None = None
    previous_average: Decimal | None = None
    change: Decimal | None = None


class LoadHealthCorrelation(BaseModel):
    load_metric: str
    health_score_category: str
    lag_days: int = 1
    paired_days: int
    coefficient: Decimal
    direction: str
    strength: str


class TrainingLoadResponse(BaseModel):
    user_id: UUID
    generated_at: datetime
    window_days: int
    baseline_days: int
    current_period: TrainingPeriodSummary
    previous_period: TrainingPeriodSummary
    metrics: list[LoadMetricComparison]
    muscle_groups: list[MuscleGroupLoad]
    health_scores: list[HealthScoreContext]
    load_health_correlations: list[LoadHealthCorrelation]
    interpretation_notes: list[str]
