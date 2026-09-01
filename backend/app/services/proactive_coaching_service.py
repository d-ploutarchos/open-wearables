from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.database import DbSession
from app.repositories.coaching_event_repository import CoachingEventRepository
from app.schemas.coaching_events import CoachingSignal, ProactiveCoachingPreview
from app.schemas.training_load import TrainingLoadResponse
from app.services.coaching_progress_service import coaching_progress_service
from app.services.training_load_service import training_load_service


class ProactiveCoachingService:
    """Build evidence packages that an external agent can turn into coaching."""

    LOCAL_DELIVERY_HOUR = 8
    RECOVERY_DECLINE_THRESHOLD = Decimal("-8")
    LARGE_SPIKE_RATIO = Decimal("1.75")

    def __init__(self) -> None:
        self.repository = CoachingEventRepository()

    @staticmethod
    def _parse_offset(value: str | None) -> timezone:
        if not value or len(value) != 6 or value[0] not in "+-" or value[3] != ":":
            return timezone.utc
        try:
            sign = 1 if value[0] == "+" else -1
            delta = timedelta(hours=int(value[1:3]), minutes=int(value[4:6])) * sign
            return timezone(delta)
        except ValueError:
            return timezone.utc

    @classmethod
    def _load_signals(cls, load: TrainingLoadResponse) -> list[CoachingSignal]:
        spikes = [metric for metric in load.metrics if metric.direction == "spike" and metric.current > 0]
        declining = [
            score
            for score in load.health_scores
            if score.change is not None
            and score.change <= cls.RECOVERY_DECLINE_THRESHOLD
            and score.category in {"sleep", "recovery", "readiness", "resilience", "body_battery"}
        ]
        material_spike = len(spikes) >= 2 or any(
            metric.recent_to_baseline_ratio is not None and metric.recent_to_baseline_ratio >= cls.LARGE_SPIKE_RATIO
            for metric in spikes
        )
        combined = bool(spikes and declining)
        if not material_spike and not combined:
            return []

        signals = [
            CoachingSignal(
                kind="workload_spike",
                severity=(
                    "high"
                    if metric.recent_to_baseline_ratio is not None and metric.recent_to_baseline_ratio >= 2
                    else "moderate"
                ),
                metric=metric.metric,
                current=float(metric.current),
                baseline=float(metric.baseline_window_average),
                ratio=float(metric.recent_to_baseline_ratio) if metric.recent_to_baseline_ratio is not None else None,
                unit=metric.unit,
            )
            for metric in spikes
        ]
        signals.extend(
            CoachingSignal(
                kind="recovery_decline_under_load",
                severity="high" if score.change is not None and score.change <= -15 else "moderate",
                metric=score.category,
                current=float(score.current_average or score.latest_value or 0),
                baseline=float(score.previous_average) if score.previous_average is not None else None,
                change=float(score.change) if score.change is not None else None,
                unit="score",
            )
            for score in declining
        )
        return signals

    @staticmethod
    def _period_key(local_now: datetime) -> str:
        year, week, _weekday = local_now.isocalendar()
        return f"{year}-W{week:02d}"

    def preview(
        self,
        db: DbSession,
        user_id: UUID,
        *,
        generated_at: datetime | None = None,
    ) -> ProactiveCoachingPreview:
        now = generated_at or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        offset_value = self.repository.latest_zone_offset(db, user_id) or "+00:00"
        local_now = now.astimezone(self._parse_offset(offset_value))
        load = training_load_service.get_training_load(db, user_id, generated_at=now)
        period_key = self._period_key(local_now)
        common: dict[str, Any] = {
            "user_id": str(user_id),
            "generated_at": now.isoformat(),
            "local_date": local_now.date().isoformat(),
            "zone_offset": offset_value,
            "evidence_policy": "Observational signals only; do not claim causation, diagnosis, or injury risk.",
        }
        weekly_due = local_now.weekday() == 0
        weekly = None
        if weekly_due:
            progress = coaching_progress_service.get_progress(db, user_id, generated_at=now)
            weekly = {
                **common,
                "period_key": period_key,
                "training_load": load.model_dump(mode="json"),
                "progress": progress.model_dump(mode="json"),
            }

        signals = self._load_signals(load)
        alert = None
        if signals and not weekly_due:
            alert = {
                **common,
                "signals": [signal.model_dump(mode="json") for signal in signals],
                "training_load": load.model_dump(mode="json"),
            }
        return ProactiveCoachingPreview(
            user_id=user_id,
            generated_at=now,
            local_date=local_now.date().isoformat(),
            zone_offset=offset_value,
            weekly_review_due=weekly_due,
            weekly_review=weekly,
            load_alert=alert,
        )


proactive_coaching_service = ProactiveCoachingService()
