from datetime import datetime
from logging import getLogger
from uuid import UUID

from celery import shared_task

from app.database import SessionLocal
from app.services.performance_record_service import performance_record_service
from app.utils.structured_logging import log_structured

logger = getLogger(__name__)


@shared_task
def backfill_strength_performance_records(
    user_id: str | None = None,
    start_datetime: str | None = None,
    limit: int = 500,
) -> dict[str, int]:
    """Silently derive strength efforts and PR history from canonical workouts."""
    parsed_start = datetime.fromisoformat(start_datetime.replace("Z", "+00:00")) if start_datetime else None
    with SessionLocal() as db:
        workouts, efforts, records_changed = performance_record_service.backfill(
            db,
            user_id=UUID(user_id) if user_id else None,
            start_datetime=parsed_start,
            limit=limit,
        )
    log_structured(
        logger,
        "info",
        "Strength performance record backfill completed",
        provider="canonical",
        action="strength_performance_backfill_completed",
        user_id=user_id,
        workouts_processed=workouts,
        efforts_processed=efforts,
        records_changed=records_changed,
    )
    return {
        "workouts_processed": workouts,
        "efforts_processed": efforts,
        "records_changed": records_changed,
    }


@shared_task
def backfill_running_performance_records(
    user_id: str | None = None,
    start_datetime: str | None = None,
    limit: int = 500,
) -> dict[str, int]:
    """Silently derive standard-distance PRs from canonical whole-run results."""
    parsed_start = datetime.fromisoformat(start_datetime.replace("Z", "+00:00")) if start_datetime else None
    with SessionLocal() as db:
        workouts, efforts, records_changed = performance_record_service.backfill_running(
            db,
            user_id=UUID(user_id) if user_id else None,
            start_datetime=parsed_start,
            limit=limit,
        )
    log_structured(
        logger,
        "info",
        "Running performance record backfill completed",
        provider="canonical",
        action="running_performance_backfill_completed",
        user_id=user_id,
        workouts_processed=workouts,
        efforts_processed=efforts,
        records_changed=records_changed,
    )
    return {
        "workouts_processed": workouts,
        "efforts_processed": efforts,
        "records_changed": records_changed,
    }
