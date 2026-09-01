from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.models import RunningEffort, StrengthEffort
from app.schemas.canonical_workout import CanonicalWorkoutResponse, CanonicalWorkoutSourceResponse
from app.services.performance_record_service import (
    RUNNING_ALGORITHM_VERSION,
    STRENGTH_ALGORITHM_VERSION,
    PerformanceRecordService,
    _RecordCandidate,
    canonical_workout_service,
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
        segment_start_datetime=datetime(2026, 9, 1, tzinfo=timezone.utc),
        segment_end_datetime=datetime(2026, 9, 1, tzinfo=timezone.utc) + timedelta(seconds=float(duration)),
        calculation_method="whole_run",
        confidence="high",
        algorithm_version=RUNNING_ALGORITHM_VERSION,
    )


def test_whole_run_eligibility_requires_standard_distance_finish() -> None:
    assert PerformanceRecordService._eligible_whole_run(Decimal("5020"), 5000) is True
    assert PerformanceRecordService._eligible_whole_run(Decimal("4900"), 5000) is False
    assert PerformanceRecordService._eligible_whole_run(Decimal("10000"), 5000) is False


def test_distance_trace_finds_constant_pace_segments() -> None:
    start = datetime(2026, 9, 1, 6, tzinfo=timezone.utc)
    samples = [(start + timedelta(seconds=index), Decimal("5")) for index in range(1000)]
    points = PerformanceRecordService._distance_trace_points(samples, start, start + timedelta(seconds=1000))

    four_hundred = PerformanceRecordService._fastest_segment(points, 400)
    five_thousand = PerformanceRecordService._fastest_segment(points, 5000)

    assert four_hundred is not None
    assert four_hundred.elapsed_seconds == Decimal("80.000")
    assert five_thousand is not None
    assert five_thousand.elapsed_seconds == Decimal("1000.000")


def test_distance_trace_selects_fastest_continuous_window() -> None:
    start = datetime(2026, 9, 1, 6, tzinfo=timezone.utc)
    increments = [Decimal("2")] * 100 + [Decimal("4")] * 100 + [Decimal("2")] * 100
    samples = [(start + timedelta(seconds=index), value) for index, value in enumerate(increments)]
    points = PerformanceRecordService._distance_trace_points(samples, start, start + timedelta(seconds=300))

    segment = PerformanceRecordService._fastest_segment(points, 200)

    assert segment is not None
    assert segment.elapsed_seconds == Decimal("50.000")
    assert segment.start_datetime == start + timedelta(seconds=100)
    assert segment.end_datetime == start + timedelta(seconds=150)


def test_running_analysis_uses_matching_granular_source() -> None:
    start = datetime(2026, 9, 1, 6, tzinfo=timezone.utc)
    canonical_id = uuid4()
    user_id = uuid4()
    sparse_source_id = uuid4()
    granular_source_id = uuid4()
    response = CanonicalWorkoutResponse(
        id=canonical_id,
        user_id=user_id,
        type="running",
        name="Run",
        start_time=start,
        end_time=start + timedelta(seconds=200),
        duration_seconds=200,
        distance_meters=1000,
        sources=[
            CanonicalWorkoutSourceResponse(
                event_record_id=sparse_source_id,
                provider="apple",
                start_time=start,
                end_time=start + timedelta(seconds=200),
            ),
            CanonicalWorkoutSourceResponse(
                event_record_id=granular_source_id,
                provider="apple",
                start_time=start,
                end_time=start + timedelta(seconds=200),
            ),
        ],
        provenance={"distance_meters": "apple"},
    )
    sparse = [(start + timedelta(seconds=index * 50), Decimal("250")) for index in range(4)]
    granular = [(start + timedelta(seconds=index), Decimal("5")) for index in range(200)]
    service = PerformanceRecordService()
    service.repository = MagicMock()
    service.repository.list_distance_samples_for_event.side_effect = lambda _db, source_id: (
        granular if source_id == granular_source_id else sparse
    )
    service.repository.get_running_effort.return_value = None
    with patch.object(canonical_workout_service, "get_response", return_value=response):
        processed, distances, returned_user_id = service._upsert_running_efforts(MagicMock(), canonical_id)

    assert processed == 3
    assert distances == {400, 800, 1000}
    assert returned_user_id == user_id
    efforts = [call.args[1] for call in service.repository.save_running_effort.call_args_list]
    assert all(effort.event_record_id == granular_source_id for effort in efforts)
    assert all(effort.calculation_method == "distance_samples" for effort in efforts)


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
