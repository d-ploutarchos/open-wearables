from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class HevySet(BaseModel):
    index: int
    type: str = "normal"
    weight_kg: Decimal | None = None
    reps: int | None = None
    distance_meters: Decimal | None = None
    duration_seconds: int | None = None
    rpe: Decimal | None = None
    custom_metric: Decimal | None = None


class HevyExercise(BaseModel):
    index: int
    title: str
    notes: str | None = None
    exercise_template_id: str
    supersets_id: int | str | None = None
    sets: list[HevySet] = Field(default_factory=list)


class HevyWorkout(BaseModel):
    id: str
    title: str
    routine_id: str | None = None
    description: str | None = None
    start_time: datetime
    end_time: datetime
    updated_at: datetime | None = None
    created_at: datetime | None = None
    exercises: list[HevyExercise] = Field(default_factory=list)


class HevyWorkoutPage(BaseModel):
    page: int | None = None
    page_count: int | None = None
    workouts: list[HevyWorkout] = Field(default_factory=list)


class HevyWorkoutEvent(BaseModel):
    type: str
    workout: HevyWorkout | None = None
    id: str | None = None
    deleted_at: datetime | None = None


class HevyWorkoutEventsPage(BaseModel):
    page: int
    page_count: int
    events: list[HevyWorkoutEvent] = Field(default_factory=list)


class HevyWebhookPayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    workout_id: str = Field(alias="workoutId")


class HevyConnectionRequest(BaseModel):
    api_key: SecretStr = Field(min_length=1)


class HevyConnectionResponse(BaseModel):
    connection_id: UUID
    provider_user_id: str
    provider_username: str | None = None
    webhook_url: str
    webhook_authorization: str | None = None
    connected_at: datetime
    last_synced_at: datetime | None = None
    last_webhook_at: datetime | None = None


class HevyConnectionStatus(BaseModel):
    connected: bool
    connection_id: UUID | None = None
    provider_username: str | None = None
    webhook_url: str | None = None
    last_synced_at: datetime | None = None
    last_webhook_at: datetime | None = None


class HevySyncResponse(BaseModel):
    status: str
    requested_at: datetime


class HevyExerciseHistoryPoint(BaseModel):
    workout_id: UUID
    performed_at: datetime
    workout_title: str
    top_weight_kg: Decimal | None = None
    total_reps: int
    work_sets: int
    volume_kg: Decimal
    estimated_one_rep_max_kg: Decimal | None = None


class HevyExerciseHistoryResponse(BaseModel):
    exercise_id: UUID
    exercise_name: str
    provider_exercise_id: str
    history: list[HevyExerciseHistoryPoint]


class StrengthExerciseSummary(BaseModel):
    exercise_id: UUID
    name: str
    provider: str
    provider_exercise_id: str
    workout_count: int
    last_performed_at: datetime | None = None
