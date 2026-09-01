from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch
from uuid import UUID

from app.schemas.performance_records import CoachingProgressResponse
from app.schemas.training_load import (
    HealthScoreContext,
    LoadMetricComparison,
    TrainingLoadResponse,
    TrainingPeriodSummary,
)
from app.services.proactive_coaching_service import ProactiveCoachingService

USER_ID = UUID("00000000-0000-0000-0000-000000000001")


def _period(now: datetime, workouts: int = 3) -> TrainingPeriodSummary:
    return TrainingPeriodSummary(
        start_datetime=now,
        end_datetime=now,
        workouts=workouts,
        total_duration_minutes=Decimal("180"),
        strength_sessions=2,
        running_sessions=1,
        other_sessions=0,
        strength_work_sets=12,
        strength_volume_kg=Decimal("4000"),
        running_distance_km=Decimal("8"),
    )


def _load(now: datetime, *, directions: tuple[str, ...], sleep_change: str = "0") -> TrainingLoadResponse:
    metrics = []
    for index, direction in enumerate(directions):
        metrics.append(
            LoadMetricComparison(
                metric=("workout_duration", "strength_volume", "running_distance")[index],
                unit=("minutes", "kg", "km")[index],
                current=Decimal("180"),
                previous=Decimal("100"),
                baseline_window_average=Decimal("100"),
                recent_to_baseline_ratio=Decimal("1.8") if direction == "spike" else Decimal("1.0"),
                direction=direction,
            )
        )
    return TrainingLoadResponse(
        user_id=USER_ID,
        generated_at=now,
        window_days=7,
        baseline_days=28,
        current_period=_period(now),
        previous_period=_period(now),
        metrics=metrics,
        muscle_groups=[],
        health_scores=[
            HealthScoreContext(
                category="sleep",
                current_observations=7,
                previous_observations=7,
                latest_value=Decimal("70"),
                current_average=Decimal("70"),
                previous_average=Decimal("80"),
                change=Decimal(sleep_change),
            )
        ],
        load_health_correlations=[],
        interpretation_notes=[],
    )


def _progress(now: datetime) -> CoachingProgressResponse:
    return CoachingProgressResponse(
        user_id=USER_ID,
        generated_at=now,
        window_days=42,
        plateau_attempts=3,
        strength=[],
        running=[],
    )


def test_preview_builds_monday_review_in_latest_local_offset() -> None:
    now = datetime(2026, 9, 7, 7, 10, tzinfo=timezone.utc)  # Monday, 08:10 at +01:00
    service = ProactiveCoachingService()
    service.repository = MagicMock()
    service.repository.latest_zone_offset.return_value = "+01:00"
    with (
        patch(
            "app.services.proactive_coaching_service.training_load_service.get_training_load",
            return_value=_load(now, directions=("within_baseline",)),
        ),
        patch(
            "app.services.proactive_coaching_service.coaching_progress_service.get_progress",
            return_value=_progress(now),
        ),
    ):
        preview = service.preview(MagicMock(), USER_ID, generated_at=now)

    assert preview.local_date == "2026-09-07"
    assert preview.weekly_review_due is True
    assert preview.weekly_review is not None
    assert preview.weekly_review["period_key"] == "2026-W37"
    assert preview.load_alert is None


def test_monday_review_suppresses_same_morning_load_alert() -> None:
    now = datetime(2026, 9, 7, 7, 10, tzinfo=timezone.utc)
    service = ProactiveCoachingService()
    service.repository = MagicMock()
    service.repository.latest_zone_offset.return_value = "+01:00"
    with (
        patch(
            "app.services.proactive_coaching_service.training_load_service.get_training_load",
            return_value=_load(now, directions=("spike", "spike")),
        ),
        patch(
            "app.services.proactive_coaching_service.coaching_progress_service.get_progress",
            return_value=_progress(now),
        ),
    ):
        preview = service.preview(MagicMock(), USER_ID, generated_at=now)

    assert preview.weekly_review is not None
    assert preview.load_alert is None


def test_load_alert_requires_a_material_change() -> None:
    now = datetime(2026, 9, 1, 7, 10, tzinfo=timezone.utc)
    quiet = _load(now, directions=("spike",), sleep_change="0")
    quiet.metrics[0].recent_to_baseline_ratio = Decimal("1.6")
    assert ProactiveCoachingService._load_signals(quiet) == []

    material = _load(now, directions=("spike", "spike"), sleep_change="0")
    signals = ProactiveCoachingService._load_signals(material)
    assert [signal.kind for signal in signals] == ["workload_spike", "workload_spike"]


def test_recovery_decline_alerts_only_when_load_is_elevated() -> None:
    now = datetime(2026, 9, 1, 7, 10, tzinfo=timezone.utc)
    combined = _load(now, directions=("spike",), sleep_change="-10")
    combined.metrics[0].recent_to_baseline_ratio = Decimal("1.6")
    assert [signal.kind for signal in ProactiveCoachingService._load_signals(combined)] == [
        "workload_spike",
        "recovery_decline_under_load",
    ]

    recovery_only = _load(now, directions=("within_baseline",), sleep_change="-10")
    assert ProactiveCoachingService._load_signals(recovery_only) == []
