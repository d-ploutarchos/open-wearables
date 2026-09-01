from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

from app.models import CanonicalWorkout, StrengthEffort
from app.services.canonical_workout_service import canonical_workout_service
from app.services.performance_record_service import STRENGTH_ALGORITHM_VERSION
from app.services.training_load_service import TrainingLoadService

USER_ID = UUID("00000000-0000-0000-0000-000000000001")
EXERCISE_ID = UUID("00000000-0000-0000-0000-000000000002")
NOW = datetime(2026, 9, 1, 12, tzinfo=timezone.utc)


def _workout(days_ago: int, workout_type: str, duration_minutes: int) -> CanonicalWorkout:
    start = NOW - timedelta(days=days_ago)
    return CanonicalWorkout(
        id=uuid4(),
        user_id=USER_ID,
        fingerprint=str(uuid4()),
        workout_type=workout_type,
        name="Run" if workout_type == "running" else "Strength",
        start_datetime=start,
        end_datetime=start + timedelta(minutes=duration_minutes),
        running_pr_algorithm_version=None,
        updated_at=NOW,
    )


def _effort(workout: CanonicalWorkout, volume: str) -> StrengthEffort:
    return StrengthEffort(
        id=uuid4(),
        user_id=USER_ID,
        canonical_workout_id=workout.id,
        event_record_id=uuid4(),
        exercise_definition_id=EXERCISE_ID,
        exercise_set_id=uuid4(),
        performed_at=workout.start_datetime,
        set_type="normal",
        repetitions=5,
        load_kg=Decimal(volume) / Decimal(5),
        volume_kg=Decimal(volume),
        estimated_one_rep_max_kg=Decimal(volume) / Decimal(4),
        algorithm_version=STRENGTH_ALGORITHM_VERSION,
    )


def _score(days_ago: int, value: str, provider: str = "internal") -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        category="sleep",
        provider=provider,
        value=Decimal(value),
        recorded_at=NOW - timedelta(days=days_ago),
    )


def test_training_load_compares_periods_baseline_muscles_and_sleep() -> None:
    current_strength = _workout(2, "strength_training", 60)
    current_run = _workout(3, "running", 30)
    previous_strength = _workout(10, "strength_training", 45)
    baseline_strength = _workout(20, "strength_training", 40)
    baseline_run = _workout(18, "running", 25)
    workouts = [baseline_strength, baseline_run, previous_strength, current_run, current_strength]
    definition = SimpleNamespace(id=EXERCISE_ID, name="Squat", primary_muscle_group="legs")
    effort_contexts = [
        (_effort(baseline_strength, "300"), definition),
        (_effort(previous_strength, "400"), definition),
        (_effort(current_strength, "500"), definition),
    ]
    scores = [
        _score(10, "70"),
        _score(3, "80"),
        _score(3, "60", provider="other"),
        _score(1, "90"),
    ]
    service = TrainingLoadService()
    service.repository = MagicMock()
    service.repository.list_workouts.return_value = workouts
    service.repository.list_strength_efforts.return_value = effort_contexts
    service.repository.list_health_scores.return_value = scores
    service.repository.provider_priorities.return_value = {"internal": 1, "other": 2}
    distances = {current_run.id: 5000, baseline_run.id: 4000}

    def response_for(_db: object, workout_id: UUID, _user_id: UUID) -> SimpleNamespace:
        return SimpleNamespace(distance_meters=distances[workout_id])

    with patch.object(canonical_workout_service, "get_response", side_effect=response_for):
        result = service.get_training_load(MagicMock(), USER_ID, generated_at=NOW)

    assert result.current_period.workouts == 2
    assert result.current_period.total_duration_minutes == Decimal("90.0")
    assert result.current_period.strength_volume_kg == Decimal("500.0")
    assert result.current_period.running_distance_km == Decimal("5.00")
    assert result.previous_period.workouts == 1
    assert result.previous_period.strength_volume_kg == Decimal("400.0")

    metrics = {item.metric: item for item in result.metrics}
    assert metrics["workout_duration"].direction == "spike"
    assert metrics["strength_volume"].current_vs_previous_percent == Decimal("25.0")
    assert metrics["running_distance"].current == Decimal("5.00")

    legs = result.muscle_groups[0]
    assert legs.muscle_group == "legs"
    assert legs.current_work_sets == 1
    assert legs.previous_work_sets == 1
    assert legs.volume_change_percent == Decimal("25.0")

    sleep = result.health_scores[0]
    assert sleep.current_observations == 2
    assert sleep.current_average == Decimal("85.0")
    assert sleep.previous_average == Decimal("70.0")
    assert sleep.change == Decimal("15.0")


def test_direction_does_not_claim_injury_risk() -> None:
    assert TrainingLoadService._direction(Decimal("160"), Decimal("100")) == ("spike", Decimal("1.60"))
    assert TrainingLoadService._direction(Decimal("100"), Decimal("100")) == (
        "within_baseline",
        Decimal("1.00"),
    )
