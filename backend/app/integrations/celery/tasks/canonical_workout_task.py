from logging import getLogger
from uuid import UUID

from celery import shared_task

from app.database import SessionLocal
from app.models import DataSource, EventRecord, WorkoutDetails
from app.schemas.enums import ProviderName
from app.schemas.model_crud.activities import EventRecordDetailCreate
from app.services.event_record_service import event_record_service
from app.utils.structured_logging import log_structured

logger = getLogger(__name__)


def _overlap_ratio(left: EventRecord, right: EventRecord) -> float:
    overlap = max(
        0.0,
        (min(left.end_datetime, right.end_datetime) - max(left.start_datetime, right.start_datetime)).total_seconds(),
    )
    shortest = min(
        max(0.0, (left.end_datetime - left.start_datetime).total_seconds()),
        max(0.0, (right.end_datetime - right.start_datetime).total_seconds()),
    )
    return overlap / shortest if shortest > 0 else 0.0


@shared_task
def emit_apple_strength_workout_after_dedupe(record_id: str) -> dict[str, str | bool]:
    """Emit Apple strength only when no detailed Hevy copy represents the session."""
    with SessionLocal() as db:
        record = db.get(EventRecord, UUID(record_id))
        if record is None or record.data_source_id is None:
            return {"emitted": False, "reason": "record_not_found"}
        data_source = db.get(DataSource, record.data_source_id)
        detail = db.get(WorkoutDetails, record.id)
        if data_source is None or detail is None:
            return {"emitted": False, "reason": "detail_not_found"}

        hevy_records = (
            db.query(EventRecord)
            .join(DataSource, EventRecord.data_source_id == DataSource.id)
            .filter(
                DataSource.user_id == data_source.user_id,
                DataSource.provider == ProviderName.HEVY,
                EventRecord.category == "workout",
                EventRecord.start_datetime < record.end_datetime,
                EventRecord.end_datetime > record.start_datetime,
            )
            .all()
        )
        matched = next((candidate for candidate in hevy_records if _overlap_ratio(record, candidate) >= 0.5), None)
        if matched is not None:
            log_structured(
                logger,
                "info",
                "Suppressed duplicate Apple strength workout webhook",
                provider="apple",
                action="workout_webhook_deduplicated",
                record_id=str(record.id),
                canonical_record_id=str(matched.id),
                user_id=str(data_source.user_id),
            )
            return {"emitted": False, "reason": "overlapping_hevy_workout"}

        schema = EventRecordDetailCreate(
            record_id=detail.record_id,
            heart_rate_max=detail.heart_rate_max,
            heart_rate_avg=detail.heart_rate_avg,
            energy_burned=detail.energy_burned,
            distance=detail.distance,
            average_speed=detail.average_speed,
            total_elevation_gain=detail.total_elevation_gain,
            segments=detail.segments,
        )
        event_record_service._emit_workout_webhook(record, data_source, schema)
        return {"emitted": True, "reason": "no_overlapping_hevy_workout"}
