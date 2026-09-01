from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.schemas.canonical_workout import CanonicalWorkoutResponse
from app.schemas.enums import ProviderName
from app.schemas.model_crud.activities import EventRecordDetailCreate
from app.services.canonical_workout_service import CanonicalWorkoutService
from app.services.event_record_service import EventRecordService


def _record(start_minute: int, duration_minutes: int) -> SimpleNamespace:
    start = datetime(2026, 9, 1, 10, start_minute, tzinfo=timezone.utc)
    return SimpleNamespace(start_datetime=start, end_datetime=start + timedelta(minutes=duration_minutes))


def test_overlap_ratio_matches_same_physical_workout() -> None:
    apple = _record(0, 36)
    hevy = _record(1, 35)
    separate = _record(40, 30)

    assert CanonicalWorkoutService._overlap_ratio(apple, hevy) > 0.9  # type: ignore[invalid-argument-type]
    assert CanonicalWorkoutService._overlap_ratio(apple, separate) == 0  # type: ignore[invalid-argument-type]


def test_apple_strength_webhook_is_delayed_for_canonical_dedupe() -> None:
    record_id = uuid4()
    record = MagicMock(
        id=record_id,
        category="workout",
        type="strength_training",
    )
    data_source = MagicMock(provider=ProviderName.APPLE)
    detail = EventRecordDetailCreate(record_id=record_id)

    with (
        patch("app.services.event_record_service.svix_service.is_enabled", return_value=True),
        patch("app.services.event_record_service.celery_app.send_task") as delayed,
        patch("app.services.event_record_service.on_workout_created") as emitted,
    ):
        EventRecordService._emit_event_record_webhook(record, data_source, detail)

    delayed.assert_called_once_with(
        "app.integrations.celery.tasks.canonical_workout_task.emit_canonical_strength_workout",
        args=[str(record_id)],
        countdown=15,
    )
    emitted.assert_not_called()


def test_hevy_strength_webhook_uses_same_canonical_task() -> None:
    record_id = uuid4()
    record = MagicMock(id=record_id, category="workout", type="strength_training")
    data_source = MagicMock(provider=ProviderName.HEVY)
    detail = EventRecordDetailCreate(record_id=record_id)

    with (
        patch("app.services.event_record_service.svix_service.is_enabled", return_value=True),
        patch("app.services.event_record_service.celery_app.send_task") as delayed,
        patch("app.services.event_record_service.on_workout_created") as emitted,
    ):
        EventRecordService._emit_event_record_webhook(record, data_source, detail)

    delayed.assert_called_once_with(
        "app.integrations.celery.tasks.canonical_workout_task.emit_canonical_strength_workout",
        args=[str(record_id)],
        countdown=5,
    )
    emitted.assert_not_called()


def test_canonical_enqueue_failure_does_not_break_ingestion() -> None:
    record = MagicMock(id=uuid4(), category="workout", type="strength_training")
    data_source = MagicMock(provider=ProviderName.HEVY)
    detail = EventRecordDetailCreate(record_id=record.id)

    with (
        patch("app.services.event_record_service.svix_service.is_enabled", return_value=True),
        patch(
            "app.services.event_record_service.celery_app.send_task",
            side_effect=ConnectionError("broker unavailable"),
        ),
    ):
        EventRecordService._emit_event_record_webhook(record, data_source, detail)


def test_canonical_response_merges_hevy_structure_and_apple_physiology() -> None:
    user_id = uuid4()
    canonical_id = uuid4()
    start = datetime(2026, 9, 1, 16, 0, tzinfo=timezone.utc)
    hevy_record = SimpleNamespace(
        id=uuid4(),
        source_name="Full Body B",
        start_datetime=start,
        end_datetime=start + timedelta(minutes=36),
    )
    apple_record = SimpleNamespace(
        id=uuid4(),
        source_name="Strength Training",
        start_datetime=start + timedelta(seconds=10),
        end_datetime=start + timedelta(minutes=36, seconds=5),
    )
    hevy_source = SimpleNamespace(provider=ProviderName.HEVY, device_model="Hevy")
    apple_source = SimpleNamespace(provider=ProviderName.APPLE, device_model="iPhone")
    exercises = [{"title": "Romanian Deadlift", "sets": [{"weight_kg": "90", "reps": 6}]}]
    hevy_detail = SimpleNamespace(
        energy_burned=None,
        distance=None,
        heart_rate_avg=None,
        heart_rate_max=None,
        segments=exercises,
    )
    apple_detail = SimpleNamespace(
        energy_burned=Decimal("201.693"),
        distance=None,
        heart_rate_avg=Decimal("128.50"),
        heart_rate_max=166,
        segments=None,
    )
    canonical = SimpleNamespace(
        id=canonical_id,
        user_id=user_id,
        workout_type="strength_training",
        name="Full Body B",
        start_datetime=start,
        end_datetime=start + timedelta(minutes=36),
    )
    service = CanonicalWorkoutService()
    service.repository = MagicMock()
    service.repository.get.return_value = canonical
    service.repository.get_source_contexts.return_value = [
        (apple_record, apple_source, apple_detail),
        (hevy_record, hevy_source, hevy_detail),
    ]

    response = service.get_response(MagicMock(), canonical_id, user_id)

    assert response is not None
    assert response.name == "Full Body B"
    assert response.duration_seconds == 2160
    assert response.calories_kcal == 201.693
    assert response.avg_heart_rate_bpm == 128
    assert response.exercises == exercises
    assert {source.provider for source in response.sources} == {"apple", "hevy"}
    assert response.provenance == {
        "name": "hevy",
        "duration_seconds": "hevy",
        "calories_kcal": "apple",
        "avg_heart_rate_bpm": "apple",
        "max_heart_rate_bpm": "apple",
        "exercises": "hevy",
    }


def test_canonical_history_returns_cursor_paginated_merged_workouts() -> None:
    user_id = uuid4()
    start = datetime(2026, 9, 1, 16, 0, tzinfo=timezone.utc)
    first = SimpleNamespace(id=uuid4(), start_datetime=start)
    extra = SimpleNamespace(id=uuid4(), start_datetime=start - timedelta(days=1))
    merged = CanonicalWorkoutResponse(
        id=first.id,
        user_id=user_id,
        type="strength_training",
        name="Full Body B",
        start_time=start,
        end_time=start + timedelta(minutes=36),
        duration_seconds=2160,
        sources=[],
        provenance={"name": "hevy"},
    )
    service = CanonicalWorkoutService()
    service.repository = MagicMock()
    service.repository.list_for_user.return_value = ([first, extra], 7)
    service.get_response = MagicMock(return_value=merged)  # type: ignore[method-assign]
    db = MagicMock()

    response = service.list_responses(db, user_id, search="deadlift", limit=1)

    assert response.data == [merged]
    assert response.pagination.has_more is True
    assert response.pagination.total_count == 7
    assert response.pagination.next_cursor is not None
    service.repository.list_for_user.assert_called_once_with(
        db,
        user_id,
        start_datetime=None,
        end_datetime=None,
        search="deadlift",
        cursor=None,
        limit=1,
    )


def test_historical_backfill_is_silent_and_idempotent() -> None:
    record_ids = [uuid4(), uuid4(), uuid4()]
    canonical_id = uuid4()
    service = CanonicalWorkoutService()
    service.repository = MagicMock()
    service.repository.list_unlinked_strength_record_ids.return_value = record_ids
    service.ensure_for_record = MagicMock(  # type: ignore[method-assign]
        side_effect=[SimpleNamespace(id=canonical_id), SimpleNamespace(id=canonical_id), None]
    )

    assert service.backfill(MagicMock(), limit=500) == (3, 1)
