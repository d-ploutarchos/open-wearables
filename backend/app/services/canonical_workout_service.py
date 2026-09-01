from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from app.database import DbSession
from app.models import CanonicalWorkout, DataSource, EventRecord
from app.repositories.canonical_workout_repository import CanonicalWorkoutRepository, WorkoutContext
from app.schemas.canonical_workout import CanonicalWorkoutResponse, CanonicalWorkoutSourceResponse


class CanonicalWorkoutService:
    def __init__(self) -> None:
        self.repository = CanonicalWorkoutRepository()

    @staticmethod
    def _provider(data_source: DataSource) -> str:
        return getattr(data_source.provider, "value", str(data_source.provider))

    @staticmethod
    def _overlap_ratio(left: EventRecord | CanonicalWorkout, right: EventRecord | CanonicalWorkout) -> float:
        left_start = left.start_datetime
        left_end = left.end_datetime
        right_start = right.start_datetime
        right_end = right.end_datetime
        overlap = max(0.0, (min(left_end, right_end) - max(left_start, right_start)).total_seconds())
        shortest = min(
            max(0.0, (left_end - left_start).total_seconds()),
            max(0.0, (right_end - right_start).total_seconds()),
        )
        return overlap / shortest if shortest > 0 else 0.0

    @staticmethod
    def _fingerprint(user_id: UUID, record: EventRecord) -> str:
        minute = record.start_datetime.minute - record.start_datetime.minute % 5
        bucket = record.start_datetime.replace(minute=minute, second=0, microsecond=0)
        return f"{user_id}:{record.type}:{bucket.isoformat()}"

    def ensure_for_record(self, db: DbSession, record_id: UUID) -> CanonicalWorkout | None:
        context = self.repository.get_record_context(db, record_id)
        if context is None:
            return None
        record, data_source, _ = context
        if record.category != "workout" or record.type != "strength_training":
            return None

        overlapping_canonical = self.repository.find_overlapping_canonical(
            db,
            data_source.user_id,
            record.type,
            record.start_datetime,
            record.end_datetime,
        )
        canonical = next(
            (candidate for candidate in overlapping_canonical if self._overlap_ratio(record, candidate) >= 0.5),
            None,
        )
        if canonical is None:
            canonical = self.repository.create(
                db,
                user_id=data_source.user_id,
                fingerprint=self._fingerprint(data_source.user_id, record),
                workout_type=record.type,
                name=record.source_name,
                start_time=record.start_datetime,
                end_time=record.end_datetime,
                updated_at=datetime.now(timezone.utc),
            )

        contexts = self.repository.find_overlapping_records(
            db,
            data_source.user_id,
            record.type,
            record.start_datetime,
            record.end_datetime,
        )
        matches = [item for item in contexts if self._overlap_ratio(record, item[0]) >= 0.5]
        for source_record, source, _ in matches:
            self.repository.link_source(db, canonical.id, source_record.id, self._provider(source))

        primary = self._primary(matches or [context])
        canonical.name = primary[0].source_name
        canonical.start_datetime = primary[0].start_datetime
        canonical.end_datetime = primary[0].end_datetime
        canonical.updated_at = datetime.now(timezone.utc)
        self.repository.save(db, canonical)
        return canonical

    @staticmethod
    def _primary(contexts: list[WorkoutContext]) -> WorkoutContext:
        return next((item for item in contexts if CanonicalWorkoutService._provider(item[1]) == "hevy"), contexts[0])

    @staticmethod
    def _first_detail(
        contexts: list[WorkoutContext],
        field: str,
        preferred_provider: str,
    ) -> tuple[Any | None, str | None]:
        ordered = sorted(
            contexts,
            key=lambda item: CanonicalWorkoutService._provider(item[1]) != preferred_provider,
        )
        for _, data_source, detail in ordered:
            if detail is not None and (value := getattr(detail, field, None)) is not None:
                return value, CanonicalWorkoutService._provider(data_source)
        return None, None

    def get_response(
        self,
        db: DbSession,
        canonical_id: UUID,
        user_id: UUID | None = None,
    ) -> CanonicalWorkoutResponse | None:
        canonical = self.repository.get(db, canonical_id, user_id)
        if canonical is None:
            return None
        contexts = self.repository.get_source_contexts(db, canonical.id)
        if not contexts:
            return None
        primary_record, primary_source, primary_detail = self._primary(contexts)
        primary_provider = self._provider(primary_source)

        calories, calories_provider = self._first_detail(contexts, "energy_burned", "apple")
        distance, distance_provider = self._first_detail(contexts, "distance", "apple")
        avg_hr, avg_hr_provider = self._first_detail(contexts, "heart_rate_avg", "apple")
        max_hr, max_hr_provider = self._first_detail(contexts, "heart_rate_max", "apple")
        exercises, exercises_provider = self._first_detail(contexts, "segments", "hevy")
        provenance = {
            "name": primary_provider,
            "duration_seconds": primary_provider,
        }
        for field, provider in (
            ("calories_kcal", calories_provider),
            ("distance_meters", distance_provider),
            ("avg_heart_rate_bpm", avg_hr_provider),
            ("max_heart_rate_bpm", max_hr_provider),
            ("exercises", exercises_provider),
        ):
            if provider is not None:
                provenance[field] = provider

        return CanonicalWorkoutResponse(
            id=canonical.id,
            user_id=canonical.user_id,
            type=canonical.workout_type,
            name=canonical.name,
            start_time=canonical.start_datetime,
            end_time=canonical.end_datetime,
            duration_seconds=max(0, int((primary_record.end_datetime - primary_record.start_datetime).total_seconds())),
            calories_kcal=float(calories) if calories is not None else None,
            distance_meters=float(distance) if distance is not None else None,
            avg_heart_rate_bpm=int(avg_hr) if avg_hr is not None else None,
            max_heart_rate_bpm=int(max_hr) if max_hr is not None else None,
            exercises=exercises if isinstance(exercises, list) else primary_detail.segments if primary_detail else None,
            sources=[
                CanonicalWorkoutSourceResponse(
                    event_record_id=source_record.id,
                    provider=self._provider(source),
                    device=source.device_model,
                    start_time=source_record.start_datetime,
                    end_time=source_record.end_datetime,
                )
                for source_record, source, _ in contexts
            ],
            provenance=provenance,
        )


canonical_workout_service = CanonicalWorkoutService()
