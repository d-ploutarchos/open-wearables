from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import BaseDbModel
from app.mappings import FKUser, PrimaryKey, str_50, str_100, str_255


class DeliveryReceipt(BaseDbModel):
    """Durable checkpoint emitted while a health event travels to an agent."""

    __tablename__ = "delivery_receipt"
    __table_args__ = (
        Index("uq_delivery_receipt_event_stage", "user_id", "event_id", "stage", unique=True),
        Index("ix_delivery_receipt_user_occurred", "user_id", "occurred_at"),
    )

    id: Mapped[PrimaryKey[UUID]]
    user_id: Mapped[FKUser]
    event_id: Mapped[str_255]
    event_type: Mapped[str_100]
    stage: Mapped[str_50]
    source: Mapped[str_100]
    occurred_at: Mapped[datetime]
    latency_ms: Mapped[int | None]
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
