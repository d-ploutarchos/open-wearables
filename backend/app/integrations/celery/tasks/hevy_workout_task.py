from datetime import datetime, timedelta, timezone
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


@shared_task
def reconcile_all_hevy_workouts() -> dict[str, int]:
    """Recover new or edited workouts when a provider webhook is missed."""
    connection_repo = hevy_workouts.connection_repo
    now = datetime.now(timezone.utc)
    synced = 0
    failed = 0
    with SessionLocal() as db:
        connections = connection_repo.get_all_active_by_provider(db, "hevy")
        for connection in connections:
            since = connection.last_synced_at or now - timedelta(days=1)
            try:
                hevy_workouts.load_data(db, connection.user_id, start=since, end=now)
                connection.last_synced_at = now
                connection.updated_at = now
                db.add(connection)
                db.commit()
                synced += 1
            except Exception:
                db.rollback()
                failed += 1
                logger.exception("Hevy reconciliation failed for user %s", connection.user_id)
    return {"synced": synced, "failed": failed}
