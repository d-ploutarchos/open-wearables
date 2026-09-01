import re
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import delete, select

from app.database import DbSession
from app.models import ExerciseDefinition, ExerciseSet, WorkoutExercise
from app.schemas.enums import ProviderName
from app.schemas.providers.hevy import HevyWorkout


def normalize_exercise_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _definition_for(
    db: DbSession,
    user_id: UUID,
    provider_exercise_id: str,
    title: str,
) -> ExerciseDefinition:
    definition = db.scalar(
        select(ExerciseDefinition).where(
            ExerciseDefinition.user_id == user_id,
            ExerciseDefinition.provider == ProviderName.HEVY,
            ExerciseDefinition.provider_exercise_id == provider_exercise_id,
        )
    )
    if definition is None:
        definition = ExerciseDefinition(
            id=uuid4(),
            user_id=user_id,
            provider=ProviderName.HEVY,
            provider_exercise_id=provider_exercise_id,
            name=title,
            normalized_name=normalize_exercise_name(title),
            equipment=None,
            primary_muscle_group=None,
            is_custom=False,
        )
        db.add(definition)
        db.flush()
    elif definition.name != title:
        definition.name = title
        definition.normalized_name = normalize_exercise_name(title)
    return definition


def replace_strength_details(
    db: DbSession,
    user_id: UUID,
    record_id: UUID,
    workout: HevyWorkout,
) -> None:
    """Replace the queryable exercise tree for an idempotent workout upsert."""
    db.execute(delete(WorkoutExercise).where(WorkoutExercise.record_id == record_id))
    db.flush()

    for exercise in sorted(workout.exercises, key=lambda item: item.index):
        definition = _definition_for(
            db,
            user_id,
            exercise.exercise_template_id,
            exercise.title,
        )
        occurrence = WorkoutExercise(
            id=uuid4(),
            record_id=record_id,
            exercise_definition_id=definition.id,
            exercise_index=exercise.index,
            title_at_time=exercise.title,
            notes=exercise.notes,
            superset_id=str(exercise.supersets_id) if exercise.supersets_id is not None else None,
        )
        db.add(occurrence)
        db.flush()

        for item in sorted(exercise.sets, key=lambda row: row.index):
            db.add(
                ExerciseSet(
                    id=uuid4(),
                    workout_exercise_id=occurrence.id,
                    set_index=item.index,
                    set_type=item.type,
                    weight_kg=item.weight_kg,
                    reps=item.reps,
                    distance_meters=item.distance_meters,
                    duration_seconds=item.duration_seconds,
                    rpe=item.rpe,
                    custom_metric=item.custom_metric,
                )
            )


def workout_segments(workout: HevyWorkout) -> list[dict]:
    """Keep a convenient denormalized representation on WorkoutDetails too."""
    return [exercise.model_dump(mode="json") for exercise in workout.exercises]


def total_volume(workout: HevyWorkout) -> Decimal:
    return sum(
        (
            (item.weight_kg or Decimal(0)) * (item.reps or 0)
            for exercise in workout.exercises
            for item in exercise.sets
            if item.type != "warmup"
        ),
        Decimal(0),
    )
