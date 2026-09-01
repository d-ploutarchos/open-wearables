from datetime import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func

from app.database import DbSession
from app.models import EventRecord, ExerciseDefinition, ExerciseSet, WorkoutExercise
from app.schemas.providers.hevy import (
    HevyExerciseHistoryPoint,
    HevyExerciseHistoryResponse,
    StrengthExerciseSummary,
)
from app.services import ApiKeyDep

router = APIRouter()


@router.get("/users/{user_id}/strength/exercises")
def list_strength_exercises(
    user_id: UUID,
    db: DbSession,
    _api_key: ApiKeyDep,
    search: Annotated[str | None, Query(max_length=100)] = None,
) -> list[StrengthExerciseSummary]:
    """List stable exercise identities available for longitudinal strength queries."""
    query = (
        db.query(
            ExerciseDefinition,
            func.count(func.distinct(EventRecord.id)).label("workout_count"),
            func.max(EventRecord.start_datetime).label("last_performed_at"),
        )
        .outerjoin(WorkoutExercise, WorkoutExercise.exercise_definition_id == ExerciseDefinition.id)
        .outerjoin(EventRecord, EventRecord.id == WorkoutExercise.record_id)
        .filter(ExerciseDefinition.user_id == user_id)
        .group_by(ExerciseDefinition.id)
        .order_by(func.max(EventRecord.start_datetime).desc().nullslast(), ExerciseDefinition.name)
    )
    if search:
        query = query.filter(ExerciseDefinition.normalized_name.ilike(f"%{search.strip().lower()}%"))
    return [
        StrengthExerciseSummary(
            exercise_id=definition.id,
            name=definition.name,
            provider=getattr(definition.provider, "value", definition.provider),
            provider_exercise_id=definition.provider_exercise_id,
            workout_count=workout_count,
            last_performed_at=last_performed_at,
        )
        for definition, workout_count, last_performed_at in query.all()
    ]


@router.get("/users/{user_id}/strength/exercises/{exercise_id}/history")
def get_strength_exercise_history(
    user_id: UUID,
    exercise_id: UUID,
    db: DbSession,
    _api_key: ApiKeyDep,
    start_datetime: datetime | None = None,
    end_datetime: datetime | None = None,
) -> HevyExerciseHistoryResponse:
    """Return workout-by-workout progress metrics derived from completed sets."""
    definition = (
        db.query(ExerciseDefinition)
        .filter(ExerciseDefinition.id == exercise_id, ExerciseDefinition.user_id == user_id)
        .one_or_none()
    )
    if definition is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exercise not found")

    query = (
        db.query(EventRecord, WorkoutExercise, ExerciseSet)
        .join(WorkoutExercise, WorkoutExercise.record_id == EventRecord.id)
        .join(ExerciseSet, ExerciseSet.workout_exercise_id == WorkoutExercise.id)
        .filter(WorkoutExercise.exercise_definition_id == exercise_id)
        .order_by(EventRecord.start_datetime.asc(), ExerciseSet.set_index.asc())
    )
    if start_datetime:
        query = query.filter(EventRecord.start_datetime >= start_datetime)
    if end_datetime:
        query = query.filter(EventRecord.start_datetime <= end_datetime)

    grouped: dict[UUID, tuple[EventRecord, list[ExerciseSet]]] = {}
    for record, _, exercise_set in query.all():
        grouped.setdefault(record.id, (record, []))[1].append(exercise_set)

    history: list[HevyExerciseHistoryPoint] = []
    for record, sets in grouped.values():
        work_sets = [item for item in sets if item.set_type != "warmup"]
        weighted: list[tuple[Decimal, int]] = [
            (item.weight_kg, item.reps) for item in work_sets if item.weight_kg is not None and item.reps is not None
        ]
        top_weight = max((weight for weight, _ in weighted), default=None)
        volume = sum((weight * reps for weight, reps in weighted), Decimal(0))
        estimated = max(
            (weight * (Decimal(1) + Decimal(reps) / Decimal(30)) for weight, reps in weighted if reps > 0),
            default=None,
        )
        history.append(
            HevyExerciseHistoryPoint(
                workout_id=record.id,
                performed_at=record.start_datetime,
                workout_title=record.source_name,
                top_weight_kg=top_weight,
                total_reps=sum(item.reps or 0 for item in work_sets),
                work_sets=len(work_sets),
                volume_kg=volume,
                estimated_one_rep_max_kg=estimated.quantize(Decimal("0.01")) if estimated else None,
            )
        )

    return HevyExerciseHistoryResponse(
        exercise_id=definition.id,
        exercise_name=definition.name,
        provider_exercise_id=definition.provider_exercise_id,
        history=history,
    )
