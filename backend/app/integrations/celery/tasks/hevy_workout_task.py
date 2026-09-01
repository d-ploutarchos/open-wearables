from logging import getLogger
from uuid import UUID

from celery import Task, shared_task

from app.database import SessionLocal
from app.services.providers.hevy.workouts import hevy_workouts
from app.utils.structured_logging import log_structured

logger = getLogger(__name__)


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_jitter=True, max_retries=5)
def ingest_hevy_workout(self: Task, user_id: str, workout_id: str) -> dict[str, str | bool]:
    """Fetch and idempotently ingest the workout referenced by a Hevy ping."""
    with SessionLocal() as db:
        record_id, created = hevy_workouts.ingest_workout_id(db, UUID(user_id), workout_id)
    log_structured(
        logger,
        "info",
        "Hevy workout ingested",
        provider="hevy",
        action="hevy_workout_ingested",
        user_id=user_id,
        workout_id=workout_id,
        record_id=str(record_id),
        created=created,
    )
    return {"record_id": str(record_id), "created": created}
