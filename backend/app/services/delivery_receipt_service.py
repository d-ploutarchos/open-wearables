from uuid import UUID

from app.database import DbSession
from app.models import DeliveryReceipt
from app.repositories.delivery_receipt_repository import DeliveryReceiptRepository
from app.schemas.delivery_receipt import DeliveryReceiptCreate, DeliveryReceiptCreateInternal


class DeliveryReceiptService:
    def __init__(self) -> None:
        self.repository = DeliveryReceiptRepository()

    def record(self, db: DbSession, user_id: UUID, payload: DeliveryReceiptCreate) -> DeliveryReceipt:
        return self.repository.upsert(
            db,
            DeliveryReceiptCreateInternal(user_id=user_id, **payload.model_dump()),
        )

    def list_recent(self, db: DbSession, user_id: UUID, limit: int) -> list[DeliveryReceipt]:
        return self.repository.list_recent(db, user_id, limit)


delivery_receipt_service = DeliveryReceiptService()
