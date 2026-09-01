from datetime import datetime, timezone
from logging import getLogger
from uuid import UUID

from celery import shared_task

from app.database import SessionLocal
from app.services.outgoing_webhooks.events import (
    on_coaching_load_alert_created,
    on_coaching_weekly_review_created,
)
from app.services.proactive_coaching_service import proactive_coaching_service
from app.utils.structured_logging import log_structured

logger = getLogger(__name__)


@shared_task(name="app.integrations.celery.tasks.proactive_coaching_task.dispatch_proactive_coaching_events")
def dispatch_proactive_coaching_events(
    user_id: str | None = None,
    generated_at: str | None = None,
    force: bool = False,
) -> dict[str, int]:
    """Emit local-morning coaching events; stable event IDs make retries harmless."""
    now = datetime.fromisoformat(generated_at.replace("Z", "+00:00")) if generated_at else datetime.now(timezone.utc)
    scanned = reviews = alerts = 0
    with SessionLocal() as db:
        user_ids = proactive_coaching_service.repository.list_user_ids(db, UUID(user_id) if user_id else None)
        for current_user_id in user_ids:
            offset = proactive_coaching_service.repository.latest_zone_offset(db, current_user_id)
            local_now = now.astimezone(proactive_coaching_service._parse_offset(offset))
            if not force and local_now.hour != proactive_coaching_service.LOCAL_DELIVERY_HOUR:
                continue
            scanned += 1
            preview = proactive_coaching_service.preview(db, current_user_id, generated_at=now)
            if preview.weekly_review is not None:
                on_coaching_weekly_review_created(
                    user_id=current_user_id,
                    period_key=preview.weekly_review["period_key"],
                    payload=preview.weekly_review,
                )
                reviews += 1
            if preview.load_alert is not None:
                on_coaching_load_alert_created(
                    user_id=current_user_id,
                    local_date=preview.local_date,
                    payload=preview.load_alert,
                )
                alerts += 1
    log_structured(
        logger,
        "info",
        "Proactive coaching scan completed",
        action="proactive_coaching_scan_completed",
        users_scanned=scanned,
        weekly_reviews=reviews,
        load_alerts=alerts,
    )
    return {"users_scanned": scanned, "weekly_reviews": reviews, "load_alerts": alerts}
