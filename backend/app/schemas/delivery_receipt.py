from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

DeliveryStage = Literal[
    "healthkit_observed",
    "sync_requested",
    "sync_completed",
    "sync_failed",
    "open_wearables_event_ready",
    "webhook_dispatched",
    "relay_received",
    "agent_message_delivered",
    "agent_delivery_failed",
]


class DeliveryReceiptCreate(BaseModel):
    event_id: str = Field(min_length=1, max_length=255)
    event_type: str = Field(min_length=1, max_length=100)
    stage: DeliveryStage
    source: str = Field(default="bionic-relay", min_length=1, max_length=100)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    latency_ms: int | None = Field(default=None, ge=0)
    detail: dict[str, Any] | None = None


class DeliveryReceiptCreateInternal(DeliveryReceiptCreate):
    id: UUID = Field(default_factory=uuid4)
    user_id: UUID


class DeliveryReceiptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    event_id: str
    event_type: str
    stage: DeliveryStage
    source: str
    occurred_at: datetime
    latency_ms: int | None
    detail: dict[str, Any] | None
    created_at: datetime
