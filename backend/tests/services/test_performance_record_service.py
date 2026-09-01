from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4

from app.models import RunningEffort, StrengthEffort
from app.services.performance_record_service import (
    RUNNING_ALGORITHM_VERSION,
    STRENGTH_ALGORITHM_VERSION,
    PerformanceRecordService,
    _RecordCandidate,
)


def _effort(*, load: str, repetitions: int, performed_at: datetime | None = None) -> StrengthEffort:
    load_kg = Decimal(load)
    return StrengthEffort(
        id=uuid4(),
        user_id=uuid4(),
        canonical_workout_id=uuid4(),
        event_record_id=uuid4(),
        exercise_definition_id=uuid4(),
        exercise_set_id=uuid4(),
        performed_at=performed_at or datetime(2026, 9, 1, tzinfo=timezone.utc),
        set_type="normal",
        repetitions=repetitions,
        load_kg=load_kg,
        volume_kg=load_kg * repetitions,
        estimated_one_rep_max_kg=PerformanceRecordService._estimated_one_rep_max(load_kg, repetitions),
        algorithm_version=STRENGTH_ALGORITHM_VERSION,
    )


def test_strength_eligibility_and_epley_guardrails() -> None:
    assert PerformanceRecordService._eligible("normal", Decimal("100"), 5) is True
    assert PerformanceRecordService._eligible("warmup", Decimal("100"), 5) is False
    assert PerformanceRecordService._eligible("normal", Decimal("0"), 5) is False
    assert PerformanceRecordService._estimated_one_rep_max(Decimal("100"), 5) == Decimal("116.667")
    assert PerformanceRecordService._estimated_one_rep_max(Decimal("100"), 13) is None


def test_strength_candidates_cover_load_rep_e1rm_and_volume_records() -> None:
    exercise_id = uuid4()
    service = PerformanceRecordService()
    efforts = [
        _effort(load="100", repetitions=5),
        _effort(load="105", repetitions=3),
        _effort(load="90", repetitions=8),
    ]

    candidates = service._candidates(exercise_id, efforts)

    assert candidates[("max_load", None)].value == Decimal("105")
    assert candidates[("rep_max", 5)].value == Decimal("100")
    assert candidates[("estimated_one_rep_max", None)].value == Decimal("116.667")
    assert candidates[("set_volume", None)].value == Decimal("720")


def test_record_sync_is_idempotent_for_same_winning_effort() -> None:
    service = PerformanceRecordService()
    service.repository = MagicMock()
    effort = _effort(load="100", repetitions=5)
    candidate = _RecordCandidate(
        record_type="estimated_one_rep_max",
        scope_key=f"exercise:{effort.exercise_definition_id}:estimated_one_rep_max",
        repetition_count=None,
        value=effort.estimated_one_rep_max_kg or Decimal(0),
        unit="kg",
        effort=effort,
    )
    db = MagicMock()
    service.repository.get_record.return_value = None

    record, first_change, first_previous = service._sync_candidate(
        db, effort.user_id, effort.exercise_definition_id, candidate
    )

    assert first_change == "created"
    assert first_previous is None
    service.repository.append_history.assert_called_once()
    service.repository.get_record.return_value = record
    service.repository.append_history.reset_mock()
    service.repository.save_record.reset_mock()

    same_record, second_change, second_previous = service._sync_candidate(
        db, effort.user_id, effort.exercise_definition_id, candidate
    )

    assert same_record.id == record.id
    assert second_change is None
    assert second_previous is None
    service.repository.append_history.assert_not_called()
    service.repository.save_record.assert_not_called()


def _running_effort(*, distance: int, seconds: str) -> RunningEffort:
    duration = Decimal(seconds)
    return RunningEffort(
        id=uuid4(),
        user_id=uuid4(),
        canonical_workout_id=uuid4(),
        event_record_id=uuid4(),
        performed_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
        target_distance_meters=distance,
        actual_distance_meters=Decimal(distance),
        elapsed_seconds=duration,
        pace_seconds_per_km=duration / Decimal(distance) * Decimal(1000),
        calculation_method="whole_run",
        confidence="high",
        algorithm_version=RUNNING_ALGORITHM_VERSION,
    )


def test_whole_run_eligibility_requires_standard_distance_finish() -> None:
    assert PerformanceRecordService._eligible_whole_run(Decimal("5020"), 5000) is True
    assert PerformanceRecordService._eligible_whole_run(Decimal("4900"), 5000) is False
    assert PerformanceRecordService._eligible_whole_run(Decimal("10000"), 5000) is False


def test_running_candidate_selects_fastest_measured_finish() -> None:
    service = PerformanceRecordService()
    slower = _running_effort(distance=5000, seconds="1500")
    faster = _running_effort(distance=5000, seconds="1425")

    candidate = service._running_candidate([slower, faster])

    assert candidate is not None
    assert candidate.value == Decimal("1425")
    assert candidate.effort.id == faster.id


def test_faster_running_time_is_an_improvement() -> None:
    service = PerformanceRecordService()
    service.repository = MagicMock()
    first = _running_effort(distance=5000, seconds="1500")
    faster = _running_effort(distance=5000, seconds="1425")
    db = MagicMock()
    service.repository.get_record.return_value = None
    first_candidate = service._running_candidate([first])
    faster_candidate = service._running_candidate([faster])
    assert first_candidate is not None
    assert faster_candidate is not None

    record, first_change, _ = service._sync_running_candidate(db, first.user_id, first_candidate)
    service.repository.get_record.return_value = record

    updated, second_change, previous = service._sync_running_candidate(
        db,
        first.user_id,
        faster_candidate,
    )

    assert first_change == "created"
    assert second_change == "improved"
    assert previous == Decimal("1500")
    assert updated.value == Decimal("1425")
