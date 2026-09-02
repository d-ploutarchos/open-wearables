from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from app.database import DbSession
from app.schemas.delivery_receipt import DeliveryReceiptCreate, DeliveryReceiptRead
from app.services.delivery_receipt_service import delivery_receipt_service
from app.utils.auth import SDKAuthDep

router = APIRouter()


def _authorize_user(user_id: UUID, auth: SDKAuthDep) -> None:
    if auth.auth_type == "sdk_token" and auth.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Token does not match user_id")


@router.post(
    "/sdk/users/{user_id}/delivery-receipts",
    status_code=status.HTTP_202_ACCEPTED,
)
def record_delivery_receipt(
    user_id: UUID,
    body: DeliveryReceiptCreate,
    db: DbSession,
    auth: SDKAuthDep,
) -> DeliveryReceiptRead:
    """Record an idempotent relay or agent-delivery checkpoint."""
    _authorize_user(user_id, auth)
    return DeliveryReceiptRead.model_validate(delivery_receipt_service.record(db, user_id, body))


@router.get("/sdk/users/{user_id}/delivery-receipts")
def list_delivery_receipts(
    user_id: UUID,
    db: DbSession,
    auth: SDKAuthDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[DeliveryReceiptRead]:
    """Return recent delivery checkpoints for Bionic diagnostics."""
    _authorize_user(user_id, auth)
    return [
        DeliveryReceiptRead.model_validate(receipt)
        for receipt in delivery_receipt_service.list_recent(db, user_id, limit)
    ]
