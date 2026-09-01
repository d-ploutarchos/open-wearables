from datetime import datetime
from typing import cast
from uuid import UUID

from app.database import DbSession
from app.models import CanonicalWorkout, ExerciseDefinition, HealthScore, ProviderPriority, StrengthEffort

StrengthLoadContext = tuple[StrengthEffort, ExerciseDefinition]


class TrainingLoadRepository:
    @staticmethod
    def list_workouts(
        db: DbSession,
        user_id: UUID,
        start_datetime: datetime,
        end_datetime: datetime,
    ) -> list[CanonicalWorkout]:
        return (
            db.query(CanonicalWorkout)
            .filter(
                CanonicalWorkout.user_id == user_id,
                CanonicalWorkout.start_datetime >= start_datetime,
                CanonicalWorkout.start_datetime < end_datetime,
            )
            .order_by(CanonicalWorkout.start_datetime.asc())
            .all()
        )

    @staticmethod
    def list_strength_efforts(
        db: DbSession,
        user_id: UUID,
        algorithm_version: str,
        start_datetime: datetime,
        end_datetime: datetime,
    ) -> list[StrengthLoadContext]:
        return cast(
            list[StrengthLoadContext],
            db.query(StrengthEffort, ExerciseDefinition)
            .join(ExerciseDefinition, ExerciseDefinition.id == StrengthEffort.exercise_definition_id)
            .filter(
                StrengthEffort.user_id == user_id,
                StrengthEffort.algorithm_version == algorithm_version,
                StrengthEffort.performed_at >= start_datetime,
                StrengthEffort.performed_at < end_datetime,
            )
            .order_by(StrengthEffort.performed_at.asc(), StrengthEffort.id.asc())
            .all(),
        )

    @staticmethod
    def list_health_scores(
        db: DbSession,
        user_id: UUID,
        start_datetime: datetime,
        end_datetime: datetime,
    ) -> list[HealthScore]:
        return (
            db.query(HealthScore)
            .filter(
                HealthScore.user_id == user_id,
                HealthScore.recorded_at >= start_datetime,
                HealthScore.recorded_at < end_datetime,
                HealthScore.value.is_not(None),
            )
            .order_by(HealthScore.recorded_at.asc(), HealthScore.id.asc())
            .all()
        )

    @staticmethod
    def provider_priorities(db: DbSession) -> dict[object, int]:
        return {item.provider: item.priority for item in db.query(ProviderPriority).all()}
