from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class CoachingSignal(BaseModel):
    kind: str
    severity: str
    metric: str
    current: float
    baseline: float | None = None
    ratio: float | None = None
    change: float | None = None
    unit: str | None = None


class ProactiveCoachingPreview(BaseModel):
    user_id: UUID
    generated_at: datetime
    local_date: str
    zone_offset: str
    weekly_review_due: bool
    weekly_review: dict[str, Any] | None = None
    load_alert: dict[str, Any] | None = None
