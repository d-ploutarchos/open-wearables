from datetime import datetime
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import or_, tuple_
from sqlalchemy.exc import IntegrityError

from app.database import DbSession
from app.models import (
    CanonicalWorkout,
    CanonicalWorkoutSource,
    DataSource,
    EventRecord,
    ExerciseDefinition,
    WorkoutDetails,
    WorkoutExercise,
)
from app.schemas.enums import ProviderName
from app.utils.pagination import decode_cursor

WorkoutContext = tuple[EventRecord, DataSource, WorkoutDetails | None]


class CanonicalWorkoutRepository:
    def get(self, db: DbSession, canonical_id: UUID, user_id: UUID | None = None) -> CanonicalWorkout | None:
        query = db.query(CanonicalWorkout).filter(CanonicalWorkout.id == canonical_id)
        if user_id is not None:
            query = query.filter(CanonicalWorkout.user_id == user_id)
        return query.one_or_none()

    def get_record_context(self, db: DbSession, record_id: UUID) -> WorkoutContext | None:
        return cast(
            WorkoutContext | None,
            db.query(EventRecord, DataSource, WorkoutDetails)
            .join(DataSource, EventRecord.data_source_id == DataSource.id)
            .outerjoin(WorkoutDetails, WorkoutDetails.record_id == EventRecord.id)
            .filter(EventRecord.id == record_id)
            .one_or_none(),
        )

    def list_for_user(
        self,
        db: DbSession,
        user_id: UUID,
        *,
        start_datetime: datetime | None = None,
        end_datetime: datetime | None = None,
        search: str | None = None,
        cursor: str | None = None,
        limit: int = 20,
    ) -> tuple[list[CanonicalWorkout], int]:
        query = db.query(CanonicalWorkout).filter(CanonicalWorkout.user_id == user_id)
        if start_datetime is not None:
            query = query.filter(CanonicalWorkout.start_datetime >= start_datetime)
        if end_datetime is not None:
            query = query.filter(CanonicalWorkout.start_datetime <= end_datetime)
        if search:
            pattern = f"%{search.strip()}%"
            exercise_match = (
                db.query(CanonicalWorkoutSource.id)
                .join(WorkoutExercise, WorkoutExercise.record_id == CanonicalWorkoutSource.event_record_id)
                .join(ExerciseDefinition, ExerciseDefinition.id == WorkoutExercise.exercise_definition_id)
                .filter(
                    CanonicalWorkoutSource.canonical_workout_id == CanonicalWorkout.id,
                    ExerciseDefinition.name.ilike(pattern),
                )
                .exists()
            )
            query = query.filter(or_(CanonicalWorkout.name.ilike(pattern), exercise_match))

        total_count = query.count()
        if cursor:
            cursor_time, cursor_id, direction = decode_cursor(cursor)
            boundary = tuple_(CanonicalWorkout.start_datetime, CanonicalWorkout.id)
            if direction == "prev":
                query = query.filter(boundary > (cursor_time, cursor_id))
            else:
                query = query.filter(boundary < (cursor_time, cursor_id))

        return (
            query.order_by(CanonicalWorkout.start_datetime.desc(), CanonicalWorkout.id.desc()).limit(limit + 1).all(),
            total_count,
        )

    def list_unlinked_record_ids(
        self,
        db: DbSession,
        *,
        workout_type: str,
        user_id: UUID | None = None,
        start_datetime: datetime | None = None,
        limit: int = 500,
    ) -> list[UUID]:
        query = (
            db.query(EventRecord.id)
            .join(DataSource, EventRecord.data_source_id == DataSource.id)
            .outerjoin(CanonicalWorkoutSource, CanonicalWorkoutSource.event_record_id == EventRecord.id)
            .filter(
                CanonicalWorkoutSource.id.is_(None),
                EventRecord.category == "workout",
                EventRecord.type == workout_type,
            )
            .order_by(EventRecord.start_datetime.asc(), EventRecord.id.asc())
        )
        if user_id is not None:
            query = query.filter(DataSource.user_id == user_id)
        if start_datetime is not None:
            query = query.filter(EventRecord.start_datetime >= start_datetime)
        return [record_id for (record_id,) in query.limit(limit).all()]

    def list_unlinked_strength_record_ids(
        self,
        db: DbSession,
        *,
        user_id: UUID | None = None,
        start_datetime: datetime | None = None,
        limit: int = 500,
    ) -> list[UUID]:
        return self.list_unlinked_record_ids(
            db,
            workout_type="strength_training",
            user_id=user_id,
            start_datetime=start_datetime,
            limit=limit,
        )

    def find_overlapping_records(
        self,
        db: DbSession,
        user_id: UUID,
        workout_type: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[WorkoutContext]:
        query = (
            db.query(EventRecord, DataSource, WorkoutDetails)
            .join(DataSource, EventRecord.data_source_id == DataSource.id)
            .outerjoin(WorkoutDetails, WorkoutDetails.record_id == EventRecord.id)
            .filter(
                DataSource.user_id == user_id,
                EventRecord.category == "workout",
                EventRecord.type == workout_type,
                EventRecord.start_datetime < end_time,
                EventRecord.end_datetime > start_time,
            )
        )
        if workout_type == "strength_training":
            query = query.filter(DataSource.provider.in_([ProviderName.HEVY, ProviderName.APPLE]))
        return cast(
            list[WorkoutContext],
            query.all(),
        )

    def find_overlapping_canonical(
        self,
        db: DbSession,
        user_id: UUID,
        workout_type: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[CanonicalWorkout]:
        return (
            db.query(CanonicalWorkout)
            .filter(
                CanonicalWorkout.user_id == user_id,
                CanonicalWorkout.workout_type == workout_type,
                CanonicalWorkout.start_datetime < end_time,
                CanonicalWorkout.end_datetime > start_time,
            )
            .all()
        )

    def create(
        self,
        db: DbSession,
        *,
        user_id: UUID,
        fingerprint: str,
        workout_type: str,
        name: str,
        start_time: datetime,
        end_time: datetime,
        updated_at: datetime,
    ) -> CanonicalWorkout:
        canonical = CanonicalWorkout(
            id=uuid4(),
            user_id=user_id,
            fingerprint=fingerprint,
            workout_type=workout_type,
            name=name,
            start_datetime=start_time,
            end_datetime=end_time,
            updated_at=updated_at,
        )
        savepoint = db.begin_nested()
        try:
            db.add(canonical)
            db.flush()
            savepoint.commit()
            return canonical
        except IntegrityError:
            savepoint.rollback()
            return (
                db.query(CanonicalWorkout)
                .filter(
                    CanonicalWorkout.user_id == user_id,
                    CanonicalWorkout.fingerprint == fingerprint,
                )
                .one()
            )

    def link_source(
        self,
        db: DbSession,
        canonical_id: UUID,
        event_record_id: UUID,
        provider: str,
    ) -> None:
        existing = (
            db.query(CanonicalWorkoutSource)
            .filter(CanonicalWorkoutSource.event_record_id == event_record_id)
            .one_or_none()
        )
        if existing is not None:
            return
        db.add(
            CanonicalWorkoutSource(
                id=uuid4(),
                canonical_workout_id=canonical_id,
                event_record_id=event_record_id,
                provider=provider,
            )
        )
        db.flush()

    def get_source_contexts(self, db: DbSession, canonical_id: UUID) -> list[WorkoutContext]:
        return cast(
            list[WorkoutContext],
            db.query(EventRecord, DataSource, WorkoutDetails)
            .join(CanonicalWorkoutSource, CanonicalWorkoutSource.event_record_id == EventRecord.id)
            .join(DataSource, EventRecord.data_source_id == DataSource.id)
            .outerjoin(WorkoutDetails, WorkoutDetails.record_id == EventRecord.id)
            .filter(CanonicalWorkoutSource.canonical_workout_id == canonical_id)
            .all(),
        )

    @staticmethod
    def save(db: DbSession, canonical: CanonicalWorkout) -> None:
        db.add(canonical)
        db.commit()
        db.refresh(canonical)
