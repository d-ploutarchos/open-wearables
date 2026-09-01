from datetime import datetime
from logging import getLogger
from uuid import UUID

from celery import shared_task

from app.database import SessionLocal
from app.services.canonical_workout_service import canonical_workout_service
from app.services.outgoing_webhooks.events import on_workout_created
from app.services.performance_record_service import performance_record_service
from app.utils.structured_logging import log_structured

logger = getLogger(__name__)


@shared_task
def backfill_canonical_strength_workouts(
    user_id: str | None = None,
    start_datetime: str | None = None,
    limit: int = 500,
) -> dict[str, int]:
    """Silently canonicalize historical or missed Apple/Hevy strength records."""
    parsed_start = datetime.fromisoformat(start_datetime.replace("Z", "+00:00")) if start_datetime else None
    with SessionLocal() as db:
        records_processed, canonical_workouts = canonical_workout_service.backfill(
            db,
            user_id=UUID(user_id) if user_id else None,
            start_datetime=parsed_start,
            limit=limit,
        )
    log_structured(
        logger,
        "info",
        "Canonical strength workout backfill completed",
        provider="canonical",
        action="canonical_workout_backfill_completed",
        user_id=user_id,
        records_processed=records_processed,
        canonical_workouts=canonical_workouts,
    )
    return {
        "records_processed": records_processed,
        "canonical_workouts": canonical_workouts,
    }


@shared_task
def emit_canonical_strength_workout(record_id: str) -> dict[str, str | bool]:
    """Correlate provider records and emit one self-contained coaching event."""
    with SessionLocal() as db:
        canonical = canonical_workout_service.ensure_for_record(db, UUID(record_id))
        if canonical is None:
            return {"emitted": False, "reason": "record_not_eligible"}
        response = canonical_workout_service.get_response(db, canonical.id)
        if response is None:
            return {"emitted": False, "reason": "canonical_workout_incomplete"}
        strength_analysis = performance_record_service.analyze_strength_workout(db, canonical.id)

        primary_provider = response.provenance.get("name", "canonical")
        primary_source = next((source for source in response.sources if source.provider == primary_provider), None)
        on_workout_created(
            record_id=response.id,
            canonical_id=response.id,
            user_id=response.user_id,
            provider=primary_provider,
            device=primary_source.device if primary_source else None,
            workout_type=response.type,
            workout_name=response.name,
            start_time=response.start_time.isoformat(),
            end_time=response.end_time.isoformat(),
            zone_offset=None,
            duration_seconds=response.duration_seconds,
            calories_kcal=response.calories_kcal,
            distance_meters=response.distance_meters,
            avg_heart_rate_bpm=response.avg_heart_rate_bpm,
            max_heart_rate_bpm=response.max_heart_rate_bpm,
            exercises=response.exercises,
            sources=[source.model_dump(mode="json") for source in response.sources],
            provenance=response.provenance,
            performance_records=[item.model_dump(mode="json") for item in strength_analysis.records_changed],
        )
        log_structured(
            logger,
            "info",
            "Canonical strength workout event emitted",
            provider="canonical",
            action="canonical_workout_emitted",
            record_id=record_id,
            canonical_workout_id=str(response.id),
            user_id=str(response.user_id),
            source_count=len(response.sources),
        )
        return {"emitted": True, "canonical_workout_id": str(response.id)}
