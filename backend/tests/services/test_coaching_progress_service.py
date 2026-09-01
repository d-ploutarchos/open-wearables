from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID, uuid4

from app.models import RunningEffort, StrengthEffort
from app.services.coaching_progress_service import CoachingProgressService
from app.services.performance_record_service import RUNNING_ALGORITHM_VERSION, STRENGTH_ALGORITHM_VERSION

USER_ID = UUID("00000000-0000-0000-0000-000000000001")
EXERCISE_ID = UUID("00000000-0000-0000-0000-000000000002")
NOW = datetime(2026, 9, 1, 12, tzinfo=timezone.utc)


def _strength_effort(days_ago: int, estimated_one_rep_max: str) -> StrengthEffort:
    value = Decimal(estimated_one_rep_max)
    return StrengthEffort(
        id=uuid4(),
        user_id=USER_ID,
        canonical_workout_id=uuid4(),
        event_record_id=uuid4(),
        exercise_definition_id=EXERCISE_ID,
        exercise_set_id=uuid4(),
        performed_at=NOW - timedelta(days=days_ago),
        set_type="normal",
        repetitions=5,
        load_kg=value / Decimal("1.166667"),
        volume_kg=value * Decimal(5),
        estimated_one_rep_max_kg=value,
        algorithm_version=STRENGTH_ALGORITHM_VERSION,
    )


def _running_effort(days_ago: int, seconds: str) -> RunningEffort:
    duration = Decimal(seconds)
    performed_at = NOW - timedelta(days=days_ago)
    return RunningEffort(
        id=uuid4(),
        user_id=USER_ID,
        canonical_workout_id=uuid4(),
        event_record_id=uuid4(),
        performed_at=performed_at,
        target_distance_meters=1000,
        actual_distance_meters=Decimal(1000),
        elapsed_seconds=duration,
        pace_seconds_per_km=duration,
        segment_start_datetime=performed_at,
        segment_end_datetime=performed_at + timedelta(seconds=float(duration)),
        calculation_method="distance_samples",
        confidence="medium",
        algorithm_version=RUNNING_ALGORITHM_VERSION,
    )


def test_progress_summarizes_strength_and_running_plateaus() -> None:
    service = CoachingProgressService()
    service.repository = MagicMock()
    definition = SimpleNamespace(id=EXERCISE_ID, name="Squat (Barbell)")
    strength_efforts = [
        _strength_effort(40, "100"),
        _strength_effort(30, "110"),
        _strength_effort(20, "108"),
        _strength_effort(10, "107"),
        _strength_effort(1, "106"),
    ]
    running_efforts = [
        _running_effort(40, "400"),
        _running_effort(30, "380"),
        _running_effort(20, "390"),
        _running_effort(10, "395"),
        _running_effort(1, "398"),
    ]
    service.repository.list_strength_effort_contexts_for_user.return_value = [
        (effort, definition) for effort in strength_efforts
    ]
    service.repository.list_running_efforts_for_user.return_value = running_efforts

    result = service.get_progress(MagicMock(), USER_ID, generated_at=NOW, window_days=42, plateau_attempts=3)

    squat = result.strength[0]
    assert squat.exercise_name == "Squat (Barbell)"
    assert squat.status == "plateau"
    assert squat.sessions == 5
    assert squat.sessions_since_best == 3
    assert squat.personal_best_estimated_one_rep_max_kg == Decimal("110")
    assert squat.latest_estimated_one_rep_max_kg == Decimal("106")
    assert squat.estimated_one_rep_max_change_from_first_kg == Decimal("6")

    one_kilometer = result.running[0]
    assert one_kilometer.status == "plateau"
    assert one_kilometer.attempts == 5
    assert one_kilometer.attempts_since_best == 3
    assert one_kilometer.personal_best_time_seconds == Decimal("380")
    assert one_kilometer.seconds_improved_from_first == Decimal("2")


def test_status_marks_recent_strict_best_as_progressing() -> None:
    status, attempts_since_best = CoachingProgressService._status(
        [Decimal("400"), Decimal("395"), Decimal("380")],
        higher_is_better=False,
        plateau_attempts=3,
    )

    assert status == "progressing"
    assert attempts_since_best == 0


def test_progress_marks_untrained_metrics_inactive() -> None:
    service = CoachingProgressService()
    service.repository = MagicMock()
    service.repository.list_strength_effort_contexts_for_user.return_value = []
    service.repository.list_running_efforts_for_user.return_value = [_running_effort(90, "400")]

    result = service.get_progress(MagicMock(), USER_ID, generated_at=NOW, window_days=42)

    assert result.running[0].status == "inactive"
    assert result.running[0].attempts_in_window == 0
