from datetime import datetime
from decimal import Decimal
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import and_

from app.database import DbSession
from app.models import (
    CanonicalWorkout,
    CanonicalWorkoutSource,
    EventRecord,
    ExerciseDefinition,
    ExerciseSet,
    PerformanceRecord,
    PerformanceRecordHistory,
    StrengthEffort,
    WorkoutExercise,
)

StrengthSetContext = tuple[CanonicalWorkout, EventRecord, ExerciseDefinition, ExerciseSet]
PerformanceRecordContext = tuple[PerformanceRecord, ExerciseDefinition | None, StrengthEffort | None]


class PerformanceRecordRepository:
    def get_strength_set_contexts(
        self,
        db: DbSession,
        canonical_workout_id: UUID,
    ) -> list[StrengthSetContext]:
        return cast(
            list[StrengthSetContext],
            db.query(CanonicalWorkout, EventRecord, ExerciseDefinition, ExerciseSet)
            .join(
                CanonicalWorkoutSource,
                CanonicalWorkoutSource.canonical_workout_id == CanonicalWorkout.id,
            )
            .join(EventRecord, EventRecord.id == CanonicalWorkoutSource.event_record_id)
            .join(WorkoutExercise, WorkoutExercise.record_id == EventRecord.id)
            .join(ExerciseDefinition, ExerciseDefinition.id == WorkoutExercise.exercise_definition_id)
            .join(ExerciseSet, ExerciseSet.workout_exercise_id == WorkoutExercise.id)
            .filter(CanonicalWorkout.id == canonical_workout_id)
            .order_by(
                EventRecord.start_datetime.asc(),
                WorkoutExercise.exercise_index.asc(),
                ExerciseSet.set_index.asc(),
            )
            .all(),
        )

    def list_strength_canonical_ids(
        self,
        db: DbSession,
        *,
        user_id: UUID | None = None,
        start_datetime: datetime | None = None,
        algorithm_version: str,
        limit: int = 500,
    ) -> list[UUID]:
        query = (
            db.query(CanonicalWorkout.id)
            .join(
                CanonicalWorkoutSource,
                CanonicalWorkoutSource.canonical_workout_id == CanonicalWorkout.id,
            )
            .join(WorkoutExercise, WorkoutExercise.record_id == CanonicalWorkoutSource.event_record_id)
            .join(ExerciseSet, ExerciseSet.workout_exercise_id == WorkoutExercise.id)
            .outerjoin(
                StrengthEffort,
                and_(
                    StrengthEffort.exercise_set_id == ExerciseSet.id,
                    StrengthEffort.algorithm_version == algorithm_version,
                ),
            )
            .filter(
                CanonicalWorkout.workout_type == "strength_training",
                ExerciseSet.set_type != "warmup",
                ExerciseSet.weight_kg.is_not(None),
                ExerciseSet.weight_kg > 0,
                ExerciseSet.reps.is_not(None),
                ExerciseSet.reps > 0,
                StrengthEffort.id.is_(None),
            )
            .group_by(CanonicalWorkout.id, CanonicalWorkout.start_datetime)
            .order_by(CanonicalWorkout.start_datetime.asc(), CanonicalWorkout.id.asc())
        )
        if user_id is not None:
            query = query.filter(CanonicalWorkout.user_id == user_id)
        if start_datetime is not None:
            query = query.filter(CanonicalWorkout.start_datetime >= start_datetime)
        return [canonical_id for (canonical_id,) in query.limit(limit).all()]

    @staticmethod
    def get_effort_for_set(
        db: DbSession,
        exercise_set_id: UUID,
        algorithm_version: str,
    ) -> StrengthEffort | None:
        return (
            db.query(StrengthEffort)
            .filter(
                StrengthEffort.exercise_set_id == exercise_set_id,
                StrengthEffort.algorithm_version == algorithm_version,
            )
            .one_or_none()
        )

    @staticmethod
    def save_effort(db: DbSession, effort: StrengthEffort) -> None:
        db.add(effort)
        db.flush()

    @staticmethod
    def list_strength_efforts(
        db: DbSession,
        user_id: UUID,
        exercise_definition_id: UUID,
        algorithm_version: str,
    ) -> list[StrengthEffort]:
        return (
            db.query(StrengthEffort)
            .filter(
                StrengthEffort.user_id == user_id,
                StrengthEffort.exercise_definition_id == exercise_definition_id,
                StrengthEffort.algorithm_version == algorithm_version,
            )
            .all()
        )

    @staticmethod
    def get_record(
        db: DbSession,
        user_id: UUID,
        sport: str,
        record_type: str,
        scope_key: str,
    ) -> PerformanceRecord | None:
        return (
            db.query(PerformanceRecord)
            .filter(
                PerformanceRecord.user_id == user_id,
                PerformanceRecord.sport == sport,
                PerformanceRecord.record_type == record_type,
                PerformanceRecord.scope_key == scope_key,
            )
            .one_or_none()
        )

    @staticmethod
    def save_record(db: DbSession, record: PerformanceRecord) -> None:
        db.add(record)
        db.flush()

    @staticmethod
    def append_history(
        db: DbSession,
        *,
        performance_record_id: UUID,
        strength_effort_id: UUID | None,
        canonical_workout_id: UUID,
        value: Decimal,
        previous_value: Decimal | None,
        achieved_at: datetime,
        algorithm_version: str,
        change_type: str,
    ) -> PerformanceRecordHistory:
        history = PerformanceRecordHistory(
            id=uuid4(),
            performance_record_id=performance_record_id,
            strength_effort_id=strength_effort_id,
            canonical_workout_id=canonical_workout_id,
            value=value,
            previous_value=previous_value,
            achieved_at=achieved_at,
            algorithm_version=algorithm_version,
            change_type=change_type,
        )
        db.add(history)
        db.flush()
        return history

    @staticmethod
    def list_records(
        db: DbSession,
        user_id: UUID,
        *,
        sport: str | None = None,
        exercise_definition_id: UUID | None = None,
        record_type: str | None = None,
        include_inactive: bool = False,
    ) -> list[PerformanceRecordContext]:
        query = (
            db.query(PerformanceRecord, ExerciseDefinition, StrengthEffort)
            .outerjoin(ExerciseDefinition, ExerciseDefinition.id == PerformanceRecord.exercise_definition_id)
            .outerjoin(StrengthEffort, StrengthEffort.id == PerformanceRecord.strength_effort_id)
            .filter(PerformanceRecord.user_id == user_id)
        )
        if not include_inactive:
            query = query.filter(PerformanceRecord.is_active.is_(True))
        if sport is not None:
            query = query.filter(PerformanceRecord.sport == sport)
        if exercise_definition_id is not None:
            query = query.filter(PerformanceRecord.exercise_definition_id == exercise_definition_id)
        if record_type is not None:
            query = query.filter(PerformanceRecord.record_type == record_type)
        return cast(
            list[PerformanceRecordContext],
            query.order_by(
                ExerciseDefinition.name.asc().nullslast(),
                PerformanceRecord.record_type.asc(),
                PerformanceRecord.repetition_count.asc().nullslast(),
            ).all(),
        )

    @staticmethod
    def list_history(
        db: DbSession,
        user_id: UUID,
        *,
        exercise_definition_id: UUID | None = None,
        record_type: str | None = None,
        limit: int = 100,
    ) -> list[tuple[PerformanceRecordHistory, PerformanceRecord, ExerciseDefinition | None]]:
        query = (
            db.query(PerformanceRecordHistory, PerformanceRecord, ExerciseDefinition)
            .join(PerformanceRecord, PerformanceRecord.id == PerformanceRecordHistory.performance_record_id)
            .outerjoin(ExerciseDefinition, ExerciseDefinition.id == PerformanceRecord.exercise_definition_id)
            .filter(PerformanceRecord.user_id == user_id)
        )
        if exercise_definition_id is not None:
            query = query.filter(PerformanceRecord.exercise_definition_id == exercise_definition_id)
        if record_type is not None:
            query = query.filter(PerformanceRecord.record_type == record_type)
        return cast(
            list[tuple[PerformanceRecordHistory, PerformanceRecord, ExerciseDefinition | None]],
            query.order_by(
                PerformanceRecordHistory.achieved_at.desc(),
                PerformanceRecordHistory.created_at.desc(),
            )
            .limit(limit)
            .all(),
        )

    @staticmethod
    def list_exercise_records(
        db: DbSession,
        user_id: UUID,
        exercise_definition_id: UUID,
    ) -> list[PerformanceRecord]:
        return (
            db.query(PerformanceRecord)
            .filter(
                PerformanceRecord.user_id == user_id,
                PerformanceRecord.sport == "strength",
                PerformanceRecord.exercise_definition_id == exercise_definition_id,
            )
            .all()
        )

    @staticmethod
    def list_orphaned_strength_record_exercises(
        db: DbSession,
        user_id: UUID | None = None,
    ) -> list[tuple[UUID, UUID]]:
        query = db.query(
            PerformanceRecord.user_id,
            PerformanceRecord.exercise_definition_id,
        ).filter(
            PerformanceRecord.sport == "strength",
            PerformanceRecord.is_active.is_(True),
            PerformanceRecord.strength_effort_id.is_(None),
            PerformanceRecord.exercise_definition_id.is_not(None),
        )
        if user_id is not None:
            query = query.filter(PerformanceRecord.user_id == user_id)
        return cast(list[tuple[UUID, UUID]], query.distinct().all())

    @staticmethod
    def commit(db: DbSession) -> None:
        db.commit()
