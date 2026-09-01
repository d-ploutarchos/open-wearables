from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.integrations.celery.tasks.canonical_workout_task import _overlap_ratio
from app.schemas.enums import ProviderName
from app.schemas.model_crud.activities import EventRecordDetailCreate
from app.services.event_record_service import EventRecordService


def _record(start_minute: int, duration_minutes: int) -> SimpleNamespace:
    start = datetime(2026, 9, 1, 10, start_minute, tzinfo=timezone.utc)
    return SimpleNamespace(start_datetime=start, end_datetime=start + timedelta(minutes=duration_minutes))


def test_overlap_ratio_matches_same_physical_workout() -> None:
    apple = _record(0, 36)
    hevy = _record(1, 35)
    separate = _record(40, 30)

    assert _overlap_ratio(apple, hevy) > 0.9
    assert _overlap_ratio(apple, separate) == 0


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
        patch(
            "app.integrations.celery.tasks.canonical_workout_task."
            "emit_apple_strength_workout_after_dedupe.apply_async"
        ) as delayed,
        patch("app.services.event_record_service.on_workout_created") as emitted,
    ):
        EventRecordService._emit_event_record_webhook(record, data_source, detail)

    delayed.assert_called_once_with(args=[str(record_id)], countdown=15)
    emitted.assert_not_called()
