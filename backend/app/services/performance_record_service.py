from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from operator import attrgetter
from uuid import UUID, uuid4

from app.database import DbSession
from app.models import PerformanceRecord, StrengthEffort
from app.repositories.performance_record_repository import PerformanceRecordRepository
from app.schemas.performance_records import (
    PerformanceRecordChangeResponse,
    PerformanceRecordHistoryResponse,
    PerformanceRecordResponse,
    StrengthAnalysisResult,
)

STRENGTH_ALGORITHM_VERSION = "strength-v1"
E1RM_MAX_REPETITIONS = 12


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

    @staticmethod
    def _response(
        record: PerformanceRecord,
        exercise_name: str | None,
        effort: StrengthEffort | None,
    ) -> PerformanceRecordResponse:
        return PerformanceRecordResponse(
            id=record.id,
            sport=record.sport,
            record_type=record.record_type,
            scope_key=record.scope_key,
            exercise_id=record.exercise_definition_id,
            exercise_name=exercise_name,
            repetition_count=record.repetition_count,
            value=record.value,
            unit=record.unit,
            achieved_at=record.achieved_at,
            canonical_workout_id=record.canonical_workout_id,
            source_effort_id=record.strength_effort_id,
            source_load_kg=effort.load_kg if effort else None,
            source_repetitions=effort.repetitions if effort else None,
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
                    **self._response(record, definition.name if definition else None, effort).model_dump(),
                    change_type=changes[record.id].change_type,
                    previous_value=changes[record.id].previous_value,
                )
                for record, definition, effort in changed_contexts
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

    def list_records(
        self,
        db: DbSession,
        user_id: UUID,
        *,
        sport: str | None = None,
        exercise_definition_id: UUID | None = None,
        record_type: str | None = None,
        include_inactive: bool = False,
    ) -> list[PerformanceRecordResponse]:
        return [
            self._response(record, definition.name if definition else None, effort)
            for record, definition, effort in self.repository.list_records(
                db,
                user_id,
                sport=sport,
                exercise_definition_id=exercise_definition_id,
                record_type=record_type,
                include_inactive=include_inactive,
            )
        ]

    def list_history(
        self,
        db: DbSession,
        user_id: UUID,
        *,
        exercise_definition_id: UUID | None = None,
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
                value=history.value,
                previous_value=history.previous_value,
                unit=record.unit,
                achieved_at=history.achieved_at,
                canonical_workout_id=history.canonical_workout_id,
                source_effort_id=history.strength_effort_id,
                algorithm_version=history.algorithm_version,
                change_type=history.change_type,
            )
            for history, record, definition in self.repository.list_history(
                db,
                user_id,
                exercise_definition_id=exercise_definition_id,
                record_type=record_type,
                limit=limit,
            )
        ]


performance_record_service = PerformanceRecordService()
