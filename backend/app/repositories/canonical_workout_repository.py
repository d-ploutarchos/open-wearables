from datetime import datetime
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError

from app.database import DbSession
from app.models import CanonicalWorkout, CanonicalWorkoutSource, DataSource, EventRecord, WorkoutDetails
from app.schemas.enums import ProviderName

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

    def find_overlapping_records(
        self,
        db: DbSession,
        user_id: UUID,
        workout_type: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[WorkoutContext]:
        return cast(
            list[WorkoutContext],
            db.query(EventRecord, DataSource, WorkoutDetails)
            .join(DataSource, EventRecord.data_source_id == DataSource.id)
            .outerjoin(WorkoutDetails, WorkoutDetails.record_id == EventRecord.id)
            .filter(
                DataSource.user_id == user_id,
                DataSource.provider.in_([ProviderName.HEVY, ProviderName.APPLE]),
                EventRecord.category == "workout",
                EventRecord.type == workout_type,
                EventRecord.start_datetime < end_time,
                EventRecord.end_datetime > start_time,
            )
            .all(),
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
