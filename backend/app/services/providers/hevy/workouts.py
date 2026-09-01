from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import delete

from app.database import DbSession
from app.models import EventRecord, WorkoutDetails
from app.repositories.event_record_repository import EventRecordRepository
from app.repositories.user_connection_repository import UserConnectionRepository
from app.schemas.enums import WorkoutType
from app.schemas.model_crud.activities import EventRecordCreate, EventRecordDetailCreate
from app.schemas.providers.hevy import HevyWorkout, HevyWorkoutEventsPage, HevyWorkoutPage
from app.services.event_record_service import event_record_service
from app.services.raw_payload_storage import store_raw_payload
from app.utils.provider_credentials import decrypt_provider_credential

from .client import HevyClient
from .strength_storage import replace_strength_details, workout_segments


class HevyWorkouts:
    """Fetch, normalize, and idempotently persist detailed Hevy workouts."""

    def __init__(self) -> None:
        self.client = HevyClient()
        self.connection_repo = UserConnectionRepository()
        self.workout_repo = EventRecordRepository(EventRecord)

    def _credentials(self, db: DbSession, user_id: UUID) -> tuple[str, UUID]:
        connection = self.connection_repo.get_active_connection(db, user_id, "hevy")
        if connection is None:
            raise ValueError("No active Hevy connection")
        return decrypt_provider_credential(connection.access_token), connection.id

    def get_workout_detail_from_api(self, db: DbSession, user_id: UUID, workout_id: str) -> HevyWorkout:
        api_key, _ = self._credentials(db, user_id)
        payload = self.client.request(api_key, f"/v1/workouts/{workout_id}")
        store_raw_payload(
            source="api_response",
            provider="hevy",
            payload=payload,
            user_id=str(user_id),
            trace_id=workout_id,
        )
        return HevyWorkout.model_validate(payload)

    def get_workouts(
        self,
        db: DbSession,
        user_id: UUID,
        start_date: datetime,
        end_date: datetime,
    ) -> list[HevyWorkout]:
        api_key, _ = self._credentials(db, user_id)
        workouts: list[HevyWorkout] = []
        page = 1
        while True:
            payload = self.client.request(api_key, "/v1/workouts", params={"page": page, "pageSize": 10})
            store_raw_payload(
                source="api_response",
                provider="hevy",
                payload=payload,
                user_id=str(user_id),
                trace_id=f"workouts-page-{page}",
            )
            parsed = HevyWorkoutPage.model_validate(payload)
            for workout in parsed.workouts:
                if workout.end_time >= start_date and workout.start_time <= end_date:
                    workouts.append(workout)
            if not parsed.workouts or (parsed.page_count is not None and page >= parsed.page_count):
                break
            if parsed.workouts[-1].end_time < start_date:
                break
            page += 1
        return workouts

    def _normalize_workout(
        self,
        workout: HevyWorkout,
        user_id: UUID,
        connection_id: UUID,
    ) -> tuple[EventRecordCreate, EventRecordDetailCreate]:
        record_id = uuid4()
        duration = max(0, int((workout.end_time - workout.start_time).total_seconds()))
        record = EventRecordCreate(
            id=record_id,
            external_id=workout.id,
            user_id=user_id,
            category="workout",
            type=WorkoutType.STRENGTH_TRAINING.value,
            source_name=workout.title or "Hevy",
            source="hevy",
            provider="hevy",
            user_connection_id=connection_id,
            device_model="Hevy",
            duration_seconds=duration,
            start_datetime=workout.start_time,
            end_datetime=workout.end_time,
        )
        detail = EventRecordDetailCreate(record_id=record_id, segments=workout_segments(workout))
        return record, detail

    def ingest_workout(self, db: DbSession, user_id: UUID, workout: HevyWorkout) -> tuple[UUID, bool]:
        _, connection_id = self._credentials(db, user_id)
        record, detail = self._normalize_workout(workout, user_id, connection_id)
        existing = self.workout_repo.get_by_external_id(db, user_id, workout.id, provider="hevy")

        if existing is not None:
            self._replace_existing(db, user_id, existing, record, detail, workout)
            return existing.id, False

        created = event_record_service.create(db, record)
        if created.id != record.id:
            # Another webhook worker inserted the same provider workout between our
            # external-id lookup and INSERT. Update it without emitting a second event.
            self._replace_existing(db, user_id, created, record, detail, workout)
            return created.id, False
        replace_strength_details(db, user_id, created.id, workout)
        event_record_service.create_detail(db, detail.model_copy(update={"record_id": created.id}))
        return created.id, True

    @staticmethod
    def _replace_existing(
        db: DbSession,
        user_id: UUID,
        existing: EventRecord,
        record: EventRecordCreate,
        detail: EventRecordDetailCreate,
        workout: HevyWorkout,
    ) -> None:
        existing.source_name = record.source_name
        existing.type = record.type
        existing.start_datetime = record.start_datetime
        existing.end_datetime = record.end_datetime
        existing.duration_seconds = record.duration_seconds
        db.execute(delete(WorkoutDetails).where(WorkoutDetails.record_id == existing.id))
        replace_strength_details(db, user_id, existing.id, workout)
        db.add(WorkoutDetails(record_id=existing.id, segments=detail.segments))
        db.commit()

    def ingest_workout_id(self, db: DbSession, user_id: UUID, workout_id: str) -> tuple[UUID, bool]:
        return self.ingest_workout(db, user_id, self.get_workout_detail_from_api(db, user_id, workout_id))

    def load_data(self, db: DbSession, user_id: UUID, **kwargs: Any) -> int:
        start = kwargs.get("start") or kwargs.get("start_date")
        end = kwargs.get("end") or kwargs.get("end_date")
        start_dt = self._coerce_datetime(start, datetime.now(timezone.utc) - timedelta(days=90))
        end_dt = self._coerce_datetime(end, datetime.now(timezone.utc))
        count = 0
        # Hevy's events endpoint only reports updates and deletes. New workouts
        # are normally announced by webhook, so a recovery pull must also scan
        # the workout list or a missed webhook would leave the workout absent.
        for workout in self.get_workouts(db, user_id, start_dt - timedelta(minutes=5), end_dt):
            self.ingest_workout(db, user_id, workout)
            count += 1
        if start_dt.year > 1970:
            count += self.reconcile_events(db, user_id, start_dt - timedelta(minutes=5))
        return count

    def reconcile_events(self, db: DbSession, user_id: UUID, since: datetime) -> int:
        """Apply updated/deleted workout events with a small overlap for delivery safety."""
        api_key, _ = self._credentials(db, user_id)
        page = 1
        processed = 0
        while True:
            payload = self.client.request(
                api_key,
                "/v1/workouts/events",
                params={"page": page, "pageSize": 10, "since": since.isoformat()},
            )
            store_raw_payload(
                source="api_response",
                provider="hevy",
                payload=payload,
                user_id=str(user_id),
                trace_id=f"workout-events-page-{page}",
            )
            parsed = HevyWorkoutEventsPage.model_validate(payload)
            for event in parsed.events:
                if event.type == "updated" and event.workout is not None:
                    self.ingest_workout(db, user_id, event.workout)
                    processed += 1
                elif event.type == "deleted" and event.id:
                    processed += self.workout_repo.delete_by_external_id(
                        db,
                        user_id,
                        event.id,
                        provider="hevy",
                    )
            if page >= parsed.page_count:
                break
            page += 1
        return processed

    @staticmethod
    def _coerce_datetime(value: Any, default: datetime) -> datetime:
        if isinstance(value, datetime):
            return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        if isinstance(value, str):
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
        return default


hevy_workouts = HevyWorkouts()
