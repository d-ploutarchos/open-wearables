from bisect import bisect_left
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from operator import attrgetter
from uuid import UUID, uuid4

from app.database import DbSession
from app.models import PerformanceRecord, RunningEffort, StrengthEffort
from app.repositories.performance_record_repository import PerformanceRecordRepository
from app.schemas.performance_records import (
    PerformanceRecordChangeResponse,
    PerformanceRecordHistoryResponse,
    PerformanceRecordResponse,
    RunningAnalysisResult,
    StrengthAnalysisResult,
)
from app.services.canonical_workout_service import canonical_workout_service

STRENGTH_ALGORITHM_VERSION = "strength-v1"
RUNNING_ALGORITHM_VERSION = "running-segments-v1"
E1RM_MAX_REPETITIONS = 12
STANDARD_RUNNING_DISTANCES = (400, 800, 1000, 1609, 2000, 5000, 10000, 21097, 42195)


@dataclass(frozen=True)
class _RecordCandidate:
    record_type: str
    scope_key: str
    repetition_count: int | None
    value: Decimal
    unit: str
    effort: StrengthEffort


@dataclass(frozen=True)
class _RecordChange:
    record: PerformanceRecord
    change_type: str
    previous_value: Decimal | None


@dataclass(frozen=True)
class _RunningRecordCandidate:
    target_distance_meters: int
    value: Decimal
    effort: RunningEffort


@dataclass(frozen=True)
class _RunningSegment:
    elapsed_seconds: Decimal
    start_datetime: datetime
    end_datetime: datetime


class PerformanceRecordService:
    def __init__(self) -> None:
        self.repository = PerformanceRecordRepository()

    @staticmethod
    def _estimated_one_rep_max(load_kg: Decimal, repetitions: int) -> Decimal | None:
        if repetitions < 1 or repetitions > E1RM_MAX_REPETITIONS:
            return None
        return (load_kg * (Decimal(1) + Decimal(repetitions) / Decimal(30))).quantize(Decimal("0.001"))

    @staticmethod
    def _eligible(set_type: str, load_kg: Decimal | None, repetitions: int | None) -> bool:
        return (
            set_type != "warmup" and load_kg is not None and load_kg > 0 and repetitions is not None and repetitions > 0
        )

    @staticmethod
    def _eligible_whole_run(actual_distance_meters: Decimal, target_distance_meters: int) -> bool:
        """Accept completed runs close to a standard distance without inventing an in-run split."""
        target = Decimal(target_distance_meters)
        minimum = target * Decimal("0.995")
        maximum = target + max(Decimal("10"), target * Decimal("0.02"))
        return minimum <= actual_distance_meters <= maximum

    @staticmethod
    def _distance_trace_points(
        samples: list[tuple[datetime, Decimal]],
        workout_start: datetime,
        workout_end: datetime,
    ) -> list[tuple[datetime, Decimal]]:
        """Convert HealthKit interval-start distance increments into cumulative endpoints."""
        if not samples or workout_end <= workout_start:
            return []
        first_time = max(workout_start, samples[0][0])
        points = [(first_time, Decimal(0))]
        cumulative = Decimal(0)
        for index, (_timestamp, value) in enumerate(samples):
            endpoint = samples[index + 1][0] if index + 1 < len(samples) else workout_end
            endpoint = min(workout_end, max(points[-1][0], endpoint))
            cumulative += value
            if endpoint == points[-1][0]:
                points[-1] = (endpoint, cumulative)
            else:
                points.append((endpoint, cumulative))
        return points

    @staticmethod
    def _interpolate_time(
        points: list[tuple[datetime, Decimal]],
        cumulative_values: list[Decimal],
        target_cumulative: Decimal,
    ) -> datetime:
        index = bisect_left(cumulative_values, target_cumulative)
        if index <= 0:
            return points[0][0]
        if index >= len(points):
            return points[-1][0]
        left_time, left_distance = points[index - 1]
        right_time, right_distance = points[index]
        if right_distance <= left_distance:
            return right_time
        fraction = float((target_cumulative - left_distance) / (right_distance - left_distance))
        return left_time + (right_time - left_time) * fraction

    @classmethod
    def _fastest_segment(
        cls,
        points: list[tuple[datetime, Decimal]],
        target_distance_meters: int,
    ) -> _RunningSegment | None:
        if len(points) < 2:
            return None
        target = Decimal(target_distance_meters)
        cumulative_values = [distance for _, distance in points]
        if cumulative_values[-1] < target:
            return None
        best: _RunningSegment | None = None

        def consider(start_time: datetime, end_time: datetime) -> None:
            nonlocal best
            seconds = Decimal(str((end_time - start_time).total_seconds())).quantize(Decimal("0.001"))
            if seconds <= 0 or target / seconds > Decimal("12"):
                return
            segment = _RunningSegment(seconds, start_time, end_time)
            if best is None or segment.elapsed_seconds < best.elapsed_seconds:
                best = segment

        for end_time, end_distance in points[1:]:
            if end_distance < target:
                continue
            start_time = cls._interpolate_time(points, cumulative_values, end_distance - target)
            consider(start_time, end_time)

        total_distance = cumulative_values[-1]
        for start_time, start_distance in points[:-1]:
            if start_distance + target > total_distance:
                break
            end_time = cls._interpolate_time(points, cumulative_values, start_distance + target)
            consider(start_time, end_time)
        return best

    def _upsert_running_efforts(
        self,
        db: DbSession,
        canonical_workout_id: UUID,
    ) -> tuple[int, set[int], UUID | None]:
        response = canonical_workout_service.get_response(db, canonical_workout_id)
        if response is None or response.type != "running" or response.distance_meters is None:
            return 0, set(), None
        actual_distance = Decimal(str(response.distance_meters))
        duration = Decimal(response.duration_seconds)
        if actual_distance <= 0 or duration <= 0 or not response.sources:
            return 0, set(), response.user_id

        distance_provider = response.provenance.get("distance_meters") or response.provenance.get("name")
        candidate_sources = [
            item for item in response.sources if item.provider == distance_provider
        ] or response.sources
        traces = []
        for candidate_source in candidate_sources:
            candidate_samples = self.repository.list_distance_samples_for_event(db, candidate_source.event_record_id)
            candidate_total = sum((value for _, value in candidate_samples), Decimal(0))
            relative_error = (
                abs(candidate_total - actual_distance) / actual_distance if candidate_total > 0 else Decimal("Infinity")
            )
            traces.append((relative_error, -len(candidate_samples), candidate_source, candidate_samples))
        _error, _sample_rank, source, samples = min(traces, key=lambda item: (item[0], item[1]))
        event_record_id = source.event_record_id
        sample_total = sum((value for _, value in samples), Decimal(0))
        trace_is_valid = (
            len(samples) >= 20
            and sample_total > 0
            and abs(sample_total - actual_distance) / actual_distance <= Decimal("0.10")
        )
        points = self._distance_trace_points(samples, response.start_time, response.end_time) if trace_is_valid else []

        processed = 0
        touched_distances: set[int] = set()
        for target_distance in STANDARD_RUNNING_DISTANCES:
            segment = self._fastest_segment(points, target_distance) if points else None
            whole_run = self._eligible_whole_run(actual_distance, target_distance)
            if segment is None and not whole_run:
                continue
            elapsed = segment.elapsed_seconds if segment else duration
            calculation_method = "distance_samples" if segment else "whole_run"
            confidence = "medium" if segment else "high"
            segment_start = segment.start_datetime if segment else response.start_time
            segment_end = segment.end_datetime if segment else response.end_time
            measured_distance = Decimal(target_distance) if segment else actual_distance
            effort = self.repository.get_running_effort(
                db,
                canonical_workout_id,
                target_distance,
                RUNNING_ALGORITHM_VERSION,
            )
            pace = (elapsed / Decimal(target_distance) * Decimal(1000)).quantize(Decimal("0.001"))
            if effort is None:
                effort = RunningEffort(
                    id=uuid4(),
                    user_id=response.user_id,
                    canonical_workout_id=canonical_workout_id,
                    event_record_id=event_record_id,
                    performed_at=response.start_time,
                    target_distance_meters=target_distance,
                    actual_distance_meters=measured_distance,
                    elapsed_seconds=elapsed,
                    pace_seconds_per_km=pace,
                    segment_start_datetime=segment_start,
                    segment_end_datetime=segment_end,
                    calculation_method=calculation_method,
                    confidence=confidence,
                    algorithm_version=RUNNING_ALGORITHM_VERSION,
                )
            else:
                effort.event_record_id = event_record_id
                effort.performed_at = response.start_time
                effort.actual_distance_meters = measured_distance
                effort.elapsed_seconds = elapsed
                effort.pace_seconds_per_km = pace
                effort.segment_start_datetime = segment_start
                effort.segment_end_datetime = segment_end
                effort.calculation_method = calculation_method
                effort.confidence = confidence
            self.repository.save_running_effort(db, effort)
            processed += 1
            touched_distances.add(target_distance)
        return processed, touched_distances, response.user_id

    def _upsert_efforts(
        self,
        db: DbSession,
        canonical_workout_id: UUID,
    ) -> tuple[int, set[UUID], UUID | None]:
        contexts = self.repository.get_strength_set_contexts(db, canonical_workout_id)
        touched_exercises = {definition.id for _, _, definition, _ in contexts}
        user_id = contexts[0][0].user_id if contexts else None
        processed = 0
        for canonical, record, definition, exercise_set in contexts:
            if not self._eligible(exercise_set.set_type, exercise_set.weight_kg, exercise_set.reps):
                continue
            load_kg = exercise_set.weight_kg
            repetitions = exercise_set.reps
            if load_kg is None or repetitions is None:
                continue
            effort = self.repository.get_effort_for_set(db, exercise_set.id, STRENGTH_ALGORITHM_VERSION)
            if effort is None:
                effort = StrengthEffort(
                    id=uuid4(),
                    user_id=canonical.user_id,
                    canonical_workout_id=canonical.id,
                    event_record_id=record.id,
                    exercise_definition_id=definition.id,
                    exercise_set_id=exercise_set.id,
                    performed_at=canonical.start_datetime,
                    set_type=exercise_set.set_type,
                    repetitions=repetitions,
                    load_kg=load_kg,
                    volume_kg=load_kg * repetitions,
                    estimated_one_rep_max_kg=self._estimated_one_rep_max(load_kg, repetitions),
                    algorithm_version=STRENGTH_ALGORITHM_VERSION,
                )
            else:
                effort.set_type = exercise_set.set_type
                effort.repetitions = repetitions
                effort.load_kg = load_kg
                effort.volume_kg = load_kg * repetitions
                effort.estimated_one_rep_max_kg = self._estimated_one_rep_max(load_kg, repetitions)
                effort.performed_at = canonical.start_datetime
            self.repository.save_effort(db, effort)
            processed += 1
        return processed, touched_exercises, user_id

    @staticmethod
    def _max_effort(efforts: list[StrengthEffort], field: str) -> StrengthEffort | None:
        eligible = [effort for effort in efforts if getattr(effort, field) is not None]
        if not eligible:
            return None
        return max(eligible, key=lambda item: (attrgetter(field)(item), -item.performed_at.timestamp()))

    def _candidates(
        self,
        exercise_id: UUID,
        efforts: list[StrengthEffort],
    ) -> dict[tuple[str, int | None], _RecordCandidate]:
        candidates: dict[tuple[str, int | None], _RecordCandidate] = {}
        for record_type, field in (
            ("max_load", "load_kg"),
            ("estimated_one_rep_max", "estimated_one_rep_max_kg"),
            ("set_volume", "volume_kg"),
        ):
            effort = self._max_effort(efforts, field)
            if effort is not None:
                candidates[(record_type, None)] = _RecordCandidate(
                    record_type=record_type,
                    scope_key=f"exercise:{exercise_id}:{record_type}",
                    repetition_count=None,
                    value=getattr(effort, field),
                    unit="kg",
                    effort=effort,
                )
        for repetitions in sorted({effort.repetitions for effort in efforts}):
            effort = self._max_effort(
                [item for item in efforts if item.repetitions == repetitions],
                "load_kg",
            )
            if effort is not None:
                candidates[("rep_max", repetitions)] = _RecordCandidate(
                    record_type="rep_max",
                    scope_key=f"exercise:{exercise_id}:rep_max:{repetitions}",
                    repetition_count=repetitions,
                    value=effort.load_kg,
                    unit="kg",
                    effort=effort,
                )
        return candidates

    def _sync_candidate(
        self,
        db: DbSession,
        user_id: UUID,
        exercise_id: UUID,
        candidate: _RecordCandidate,
    ) -> tuple[PerformanceRecord, str | None, Decimal | None]:
        now = datetime.now(timezone.utc)
        record = self.repository.get_record(
            db,
            user_id,
            "strength",
            candidate.record_type,
            candidate.scope_key,
        )
        previous_value: Decimal | None = None
        change_type: str | None = None
        if record is None:
            record = PerformanceRecord(
                id=uuid4(),
                user_id=user_id,
                sport="strength",
                record_type=candidate.record_type,
                scope_key=candidate.scope_key,
                exercise_definition_id=exercise_id,
                repetition_count=candidate.repetition_count,
                value=candidate.value,
                unit=candidate.unit,
                strength_effort_id=candidate.effort.id,
                canonical_workout_id=candidate.effort.canonical_workout_id,
                achieved_at=candidate.effort.performed_at,
                algorithm_version=STRENGTH_ALGORITHM_VERSION,
                is_active=True,
                updated_at=now,
            )
            change_type = "created"
        elif not record.is_active:
            previous_value = record.value
            change_type = "restored"
        elif record.value != candidate.value:
            previous_value = record.value
            change_type = "improved" if candidate.value > record.value else "corrected"

        source_changed = record.strength_effort_id != candidate.effort.id
        if change_type is not None or source_changed:
            record.value = candidate.value
            record.strength_effort_id = candidate.effort.id
            record.canonical_workout_id = candidate.effort.canonical_workout_id
            record.achieved_at = candidate.effort.performed_at
            record.algorithm_version = STRENGTH_ALGORITHM_VERSION
            record.is_active = True
            record.updated_at = now
            self.repository.save_record(db, record)
        if change_type is not None:
            self.repository.append_history(
                db,
                performance_record_id=record.id,
                strength_effort_id=candidate.effort.id,
                canonical_workout_id=candidate.effort.canonical_workout_id,
                value=candidate.value,
                previous_value=previous_value,
                achieved_at=candidate.effort.performed_at,
                algorithm_version=STRENGTH_ALGORITHM_VERSION,
                change_type=change_type,
            )
        return record, change_type, previous_value

    def _recompute_exercise(self, db: DbSession, user_id: UUID, exercise_id: UUID) -> list[_RecordChange]:
        efforts = self.repository.list_strength_efforts(db, user_id, exercise_id, STRENGTH_ALGORITHM_VERSION)
        candidates = self._candidates(exercise_id, efforts)
        existing = {
            (record.record_type, record.repetition_count): record
            for record in self.repository.list_exercise_records(db, user_id, exercise_id)
        }
        changed: list[_RecordChange] = []
        for key, candidate in candidates.items():
            record, change_type, previous_value = self._sync_candidate(db, user_id, exercise_id, candidate)
            if change_type is not None:
                changed.append(_RecordChange(record, change_type, previous_value))
            existing.pop(key, None)

        now = datetime.now(timezone.utc)
        for record in existing.values():
            if not record.is_active:
                continue
            previous_value = record.value
            record.is_active = False
            record.strength_effort_id = None
            record.updated_at = now
            self.repository.save_record(db, record)
            self.repository.append_history(
                db,
                performance_record_id=record.id,
                strength_effort_id=None,
                canonical_workout_id=record.canonical_workout_id,
                value=record.value,
                previous_value=previous_value,
                achieved_at=now,
                algorithm_version=STRENGTH_ALGORITHM_VERSION,
                change_type="revoked",
            )
            changed.append(_RecordChange(record, "revoked", previous_value))
        return changed

    def _running_candidate(
        self,
        efforts: list[RunningEffort],
    ) -> _RunningRecordCandidate | None:
        if not efforts:
            return None
        effort = min(efforts, key=lambda item: (item.elapsed_seconds, item.performed_at.timestamp()))
        return _RunningRecordCandidate(
            target_distance_meters=effort.target_distance_meters,
            value=effort.elapsed_seconds,
            effort=effort,
        )

    def _sync_running_candidate(
        self,
        db: DbSession,
        user_id: UUID,
        candidate: _RunningRecordCandidate,
    ) -> tuple[PerformanceRecord, str | None, Decimal | None]:
        now = datetime.now(timezone.utc)
        scope_key = f"distance:{candidate.target_distance_meters}:fastest_time"
        record = self.repository.get_record(db, user_id, "running", "fastest_time", scope_key)
        previous_value: Decimal | None = None
        change_type: str | None = None
        if record is None:
            record = PerformanceRecord(
                id=uuid4(),
                user_id=user_id,
                sport="running",
                record_type="fastest_time",
                scope_key=scope_key,
                exercise_definition_id=None,
                repetition_count=None,
                distance_meters=candidate.target_distance_meters,
                value=candidate.value,
                unit="seconds",
                strength_effort_id=None,
                running_effort_id=candidate.effort.id,
                canonical_workout_id=candidate.effort.canonical_workout_id,
                achieved_at=candidate.effort.performed_at,
                algorithm_version=RUNNING_ALGORITHM_VERSION,
                is_active=True,
                updated_at=now,
            )
            change_type = "created"
        elif not record.is_active:
            previous_value = record.value
            change_type = "restored"
        elif record.value != candidate.value:
            previous_value = record.value
            change_type = "improved" if candidate.value < record.value else "corrected"

        source_changed = record.running_effort_id != candidate.effort.id
        if change_type is not None or source_changed:
            record.distance_meters = candidate.target_distance_meters
            record.value = candidate.value
            record.running_effort_id = candidate.effort.id
            record.strength_effort_id = None
            record.canonical_workout_id = candidate.effort.canonical_workout_id
            record.achieved_at = candidate.effort.performed_at
            record.algorithm_version = RUNNING_ALGORITHM_VERSION
            record.is_active = True
            record.updated_at = now
            self.repository.save_record(db, record)
        if change_type is not None:
            self.repository.append_history(
                db,
                performance_record_id=record.id,
                strength_effort_id=None,
                running_effort_id=candidate.effort.id,
                canonical_workout_id=candidate.effort.canonical_workout_id,
                value=candidate.value,
                previous_value=previous_value,
                achieved_at=candidate.effort.performed_at,
                algorithm_version=RUNNING_ALGORITHM_VERSION,
                change_type=change_type,
            )
        return record, change_type, previous_value

    def _recompute_running(
        self, db: DbSession, user_id: UUID, distances: set[int] | None = None
    ) -> list[_RecordChange]:
        distances = distances or set(STANDARD_RUNNING_DISTANCES)
        existing = {record.distance_meters: record for record in self.repository.list_running_records(db, user_id)}
        changed: list[_RecordChange] = []
        for distance in sorted(distances):
            candidate = self._running_candidate(
                self.repository.list_running_efforts(db, user_id, distance, RUNNING_ALGORITHM_VERSION)
            )
            if candidate is None:
                continue
            record, change_type, previous_value = self._sync_running_candidate(db, user_id, candidate)
            if change_type is not None:
                changed.append(_RecordChange(record, change_type, previous_value))
            existing.pop(distance, None)

        now = datetime.now(timezone.utc)
        for distance, record in existing.items():
            if distance not in distances or not record.is_active:
                continue
            previous_value = record.value
            record.is_active = False
            record.running_effort_id = None
            record.updated_at = now
            self.repository.save_record(db, record)
            self.repository.append_history(
                db,
                performance_record_id=record.id,
                strength_effort_id=None,
                canonical_workout_id=record.canonical_workout_id,
                value=record.value,
                previous_value=previous_value,
                achieved_at=now,
                algorithm_version=RUNNING_ALGORITHM_VERSION,
                change_type="revoked",
            )
            changed.append(_RecordChange(record, "revoked", previous_value))
        return changed

    @staticmethod
    def _response(
        record: PerformanceRecord,
        exercise_name: str | None,
        effort: StrengthEffort | None,
        running_effort: RunningEffort | None,
    ) -> PerformanceRecordResponse:
        return PerformanceRecordResponse(
            id=record.id,
            sport=record.sport,
            record_type=record.record_type,
            scope_key=record.scope_key,
            exercise_id=record.exercise_definition_id,
            exercise_name=exercise_name,
            repetition_count=record.repetition_count,
            distance_meters=record.distance_meters,
            value=record.value,
            unit=record.unit,
            achieved_at=record.achieved_at,
            canonical_workout_id=record.canonical_workout_id,
            source_effort_id=record.strength_effort_id,
            source_running_effort_id=record.running_effort_id,
            source_load_kg=effort.load_kg if effort else None,
            source_repetitions=effort.repetitions if effort else None,
            source_duration_seconds=running_effort.elapsed_seconds if running_effort else None,
            source_distance_meters=running_effort.actual_distance_meters if running_effort else None,
            segment_start_datetime=running_effort.segment_start_datetime if running_effort else None,
            segment_end_datetime=running_effort.segment_end_datetime if running_effort else None,
            calculation_method=running_effort.calculation_method if running_effort else None,
            confidence=running_effort.confidence if running_effort else None,
            algorithm_version=record.algorithm_version,
            is_active=record.is_active,
        )

    def analyze_strength_workout(self, db: DbSession, canonical_workout_id: UUID) -> StrengthAnalysisResult:
        processed, exercise_ids, user_id = self._upsert_efforts(db, canonical_workout_id)
        if user_id is None:
            return StrengthAnalysisResult(
                canonical_workout_id=canonical_workout_id,
                efforts_processed=0,
                records_changed=[],
            )
        changes: dict[UUID, _RecordChange] = {}
        for exercise_id in exercise_ids:
            changes.update((change.record.id, change) for change in self._recompute_exercise(db, user_id, exercise_id))
        self.repository.commit(db)
        changed_contexts = [
            context
            for context in self.repository.list_records(db, user_id, include_inactive=True)
            if context[0].id in changes
        ]
        return StrengthAnalysisResult(
            canonical_workout_id=canonical_workout_id,
            efforts_processed=processed,
            records_changed=[
                PerformanceRecordChangeResponse(
                    **self._response(
                        record, definition.name if definition else None, effort, running_effort
                    ).model_dump(),
                    change_type=changes[record.id].change_type,
                    previous_value=changes[record.id].previous_value,
                )
                for record, definition, effort, running_effort in changed_contexts
            ],
        )

    def analyze_running_workout(self, db: DbSession, canonical_workout_id: UUID) -> RunningAnalysisResult:
        processed, distances, user_id = self._upsert_running_efforts(db, canonical_workout_id)
        self.repository.mark_running_analyzed(db, canonical_workout_id, RUNNING_ALGORITHM_VERSION)
        if user_id is None:
            self.repository.commit(db)
            return RunningAnalysisResult(
                canonical_workout_id=canonical_workout_id,
                efforts_processed=0,
                records_changed=[],
            )
        changes = {change.record.id: change for change in self._recompute_running(db, user_id, distances)}
        self.repository.commit(db)
        changed_contexts = [
            context
            for context in self.repository.list_records(db, user_id, include_inactive=True)
            if context[0].id in changes
        ]
        return RunningAnalysisResult(
            canonical_workout_id=canonical_workout_id,
            efforts_processed=processed,
            records_changed=[
                PerformanceRecordChangeResponse(
                    **self._response(record, None, strength_effort, running_effort).model_dump(),
                    change_type=changes[record.id].change_type,
                    previous_value=changes[record.id].previous_value,
                )
                for record, _definition, strength_effort, running_effort in changed_contexts
            ],
        )

    def backfill(
        self,
        db: DbSession,
        *,
        user_id: UUID | None = None,
        start_datetime: datetime | None = None,
        limit: int = 500,
    ) -> tuple[int, int, int]:
        canonical_ids = self.repository.list_strength_canonical_ids(
            db,
            user_id=user_id,
            start_datetime=start_datetime,
            algorithm_version=STRENGTH_ALGORITHM_VERSION,
            limit=limit,
        )
        efforts = 0
        changes = 0
        for canonical_id in canonical_ids:
            result = self.analyze_strength_workout(db, canonical_id)
            efforts += result.efforts_processed
            changes += len(result.records_changed)
        orphaned = self.repository.list_orphaned_strength_record_exercises(db, user_id)
        for orphan_user_id, exercise_id in orphaned:
            changes += len(self._recompute_exercise(db, orphan_user_id, exercise_id))
        if orphaned:
            self.repository.commit(db)
        return len(canonical_ids), efforts, changes

    def backfill_running(
        self,
        db: DbSession,
        *,
        user_id: UUID | None = None,
        start_datetime: datetime | None = None,
        limit: int = 500,
    ) -> tuple[int, int, int]:
        canonical_ids = self.repository.list_running_canonical_ids(
            db,
            user_id=user_id,
            start_datetime=start_datetime,
            algorithm_version=RUNNING_ALGORITHM_VERSION,
            limit=limit,
        )
        efforts = 0
        changes = 0
        for canonical_id in canonical_ids:
            result = self.analyze_running_workout(db, canonical_id)
            efforts += result.efforts_processed
            changes += len(result.records_changed)
        orphaned_users = self.repository.list_orphaned_running_record_users(db, user_id)
        for orphan_user_id in orphaned_users:
            changes += len(self._recompute_running(db, orphan_user_id))
        if orphaned_users:
            self.repository.commit(db)
        return len(canonical_ids), efforts, changes

    def list_records(
        self,
        db: DbSession,
        user_id: UUID,
        *,
        sport: str | None = None,
        exercise_definition_id: UUID | None = None,
        distance_meters: int | None = None,
        record_type: str | None = None,
        include_inactive: bool = False,
    ) -> list[PerformanceRecordResponse]:
        return [
            self._response(record, definition.name if definition else None, effort, running_effort)
            for record, definition, effort, running_effort in self.repository.list_records(
                db,
                user_id,
                sport=sport,
                exercise_definition_id=exercise_definition_id,
                distance_meters=distance_meters,
                record_type=record_type,
                include_inactive=include_inactive,
            )
        ]

    def list_history(
        self,
        db: DbSession,
        user_id: UUID,
        *,
        sport: str | None = None,
        exercise_definition_id: UUID | None = None,
        distance_meters: int | None = None,
        record_type: str | None = None,
        limit: int = 100,
    ) -> list[PerformanceRecordHistoryResponse]:
        return [
            PerformanceRecordHistoryResponse(
                id=history.id,
                performance_record_id=record.id,
                sport=record.sport,
                record_type=record.record_type,
                scope_key=record.scope_key,
                exercise_id=record.exercise_definition_id,
                exercise_name=definition.name if definition else None,
                repetition_count=record.repetition_count,
                distance_meters=record.distance_meters,
                value=history.value,
                previous_value=history.previous_value,
                unit=record.unit,
                achieved_at=history.achieved_at,
                canonical_workout_id=history.canonical_workout_id,
                source_effort_id=history.strength_effort_id,
                source_running_effort_id=history.running_effort_id,
                algorithm_version=history.algorithm_version,
                change_type=history.change_type,
            )
            for history, record, definition in self.repository.list_history(
                db,
                user_id,
                sport=sport,
                exercise_definition_id=exercise_definition_id,
                distance_meters=distance_meters,
                record_type=record_type,
                limit=limit,
            )
        ]


performance_record_service = PerformanceRecordService()
