from uuid import UUID

from sqlalchemy.orm import Session

from app.models import DeliveryReceipt
from app.schemas.delivery_receipt import DeliveryReceiptCreateInternal


class DeliveryReceiptRepository:
    """Persistence operations for idempotent agent-delivery checkpoints."""

    def upsert(self, db: Session, creator: DeliveryReceiptCreateInternal) -> DeliveryReceipt:
        receipt = (
            db.query(DeliveryReceipt)
            .filter(
                DeliveryReceipt.user_id == creator.user_id,
                DeliveryReceipt.event_id == creator.event_id,
                DeliveryReceipt.stage == creator.stage,
            )
            .one_or_none()
        )
        if receipt is None:
            receipt = DeliveryReceipt(**creator.model_dump())
        else:
            for field, value in creator.model_dump(exclude={"id", "user_id", "event_id", "stage"}).items():
                setattr(receipt, field, value)
        db.add(receipt)
        db.commit()
        db.refresh(receipt)
        return receipt

    def list_recent(self, db: Session, user_id: UUID, limit: int) -> list[DeliveryReceipt]:
        return (
            db.query(DeliveryReceipt)
            .filter(DeliveryReceipt.user_id == user_id)
            .order_by(DeliveryReceipt.occurred_at.desc())
            .limit(limit)
            .all()
        )
