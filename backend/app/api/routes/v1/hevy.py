from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID, uuid4

import httpx
from celery import current_app as celery_app
from fastapi import APIRouter, Header, HTTPException, Request, Response, status

from app.database import DbSession
from app.models import UserConnection
from app.repositories.user_connection_repository import UserConnectionRepository
from app.schemas.auth import ConnectionStatus
from app.schemas.providers.hevy import (
    HevyConnectionRequest,
    HevyConnectionResponse,
    HevyConnectionStatus,
    HevySyncResponse,
    HevyWebhookPayload,
)
from app.services.providers.hevy.client import HevyClient
from app.utils.auth import SDKAuthDep
from app.utils.provider_credentials import (
    encrypt_provider_credential,
    generate_webhook_secret,
    hash_webhook_secret,
    verify_webhook_secret,
)

router = APIRouter()
connection_repo = UserConnectionRepository()
client = HevyClient()


def _authorize_user(auth: SDKAuthDep, user_id: UUID) -> None:
    if auth.auth_type == "sdk_token" and auth.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Token does not match user_id")


def _webhook_url(request: Request, connection_id: UUID) -> str:
    """Build the callback from the public host that the mobile client used."""
    return str(request.url_for("receive_hevy_webhook", connection_id=str(connection_id)))


def _queue_full_sync(user_id: UUID, requested_at: datetime) -> None:
    celery_app.send_task(
        "app.integrations.celery.tasks.sync_vendor_data_task.sync_vendor_data",
        kwargs={
            "user_id": str(user_id),
            "start_date": "1970-01-01T00:00:00+00:00",
            "end_date": requested_at.isoformat(),
            "providers": ["hevy"],
            # A connection backfill establishes the live cursor when it succeeds.
            "is_historical": False,
        },
    )


@router.post("/sdk/users/{user_id}/connections/hevy")
def connect_hevy(
    user_id: UUID,
    payload: HevyConnectionRequest,
    request: Request,
    db: DbSession,
    auth: SDKAuthDep,
) -> HevyConnectionResponse:
    """Validate and store a user-scoped Hevy API key, returning one-time webhook credentials."""
    _authorize_user(auth, user_id)
    api_key = payload.api_key.get_secret_value().strip()
    try:
        info = client.request(api_key, "/v1/user/info")
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (400, 401, 403, 404):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Hevy rejected that API key") from exc
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Hevy could not validate the connection",
        ) from exc
    except httpx.RequestError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Hevy is currently unreachable") from exc

    profile = info.get("data") if isinstance(info.get("data"), dict) else info
    provider_user_id = str(profile.get("id") or profile.get("user_id") or "").strip()
    if not provider_user_id:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Hevy returned an invalid user profile")
    provider_username = profile.get("name") or profile.get("username")
    secret = generate_webhook_secret()
    now = datetime.now(timezone.utc)
    connection = connection_repo.get_by_user_and_provider(db, user_id, "hevy")
    if connection is None:
        connection = UserConnection(
            id=uuid4(),
            user_id=user_id,
            provider="hevy",
            provider_user_id=provider_user_id,
            provider_username=str(provider_username) if provider_username else None,
            access_token=encrypt_provider_credential(api_key),
            refresh_token=None,
            token_expires_at=None,
            scope="workouts:read",
            status=ConnectionStatus.ACTIVE,
            last_synced_at=None,
            webhook_secret_hash=hash_webhook_secret(secret),
            last_webhook_at=None,
            updated_at=now,
        )
    else:
        connection.provider_user_id = provider_user_id
        connection.provider_username = str(provider_username) if provider_username else None
        connection.access_token = encrypt_provider_credential(api_key)
        connection.status = ConnectionStatus.ACTIVE
        connection.webhook_secret_hash = hash_webhook_secret(secret)
        connection.updated_at = now
    db.add(connection)
    db.commit()
    db.refresh(connection)

    _queue_full_sync(user_id, now)
    return HevyConnectionResponse(
        connection_id=connection.id,
        provider_user_id=provider_user_id,
        provider_username=connection.provider_username,
        webhook_url=_webhook_url(request, connection.id),
        webhook_authorization=f"Bearer {secret}",
        connected_at=connection.created_at,
        last_synced_at=connection.last_synced_at,
        last_webhook_at=connection.last_webhook_at,
    )


@router.get("/sdk/users/{user_id}/connections/hevy")
def get_hevy_connection(user_id: UUID, request: Request, db: DbSession, auth: SDKAuthDep) -> HevyConnectionStatus:
    _authorize_user(auth, user_id)
    connection = connection_repo.get_active_connection(db, user_id, "hevy")
    if connection is None:
        return HevyConnectionStatus(connected=False)
    return HevyConnectionStatus(
        connected=True,
        connection_id=connection.id,
        provider_username=connection.provider_username,
        webhook_url=_webhook_url(request, connection.id),
        last_synced_at=connection.last_synced_at,
        last_webhook_at=connection.last_webhook_at,
    )


@router.post("/sdk/users/{user_id}/connections/hevy/webhook-secret")
def rotate_hevy_webhook_secret(
    user_id: UUID,
    request: Request,
    db: DbSession,
    auth: SDKAuthDep,
) -> HevyConnectionResponse:
    """Rotate and reveal a Hevy webhook bearer value once for account setup."""
    _authorize_user(auth, user_id)
    connection = connection_repo.get_active_connection(db, user_id, "hevy")
    if connection is None or not connection.provider_user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hevy is not connected")
    secret = generate_webhook_secret()
    connection.webhook_secret_hash = hash_webhook_secret(secret)
    connection.updated_at = datetime.now(timezone.utc)
    db.add(connection)
    db.commit()
    db.refresh(connection)
    return HevyConnectionResponse(
        connection_id=connection.id,
        provider_user_id=connection.provider_user_id,
        provider_username=connection.provider_username,
        webhook_url=_webhook_url(request, connection.id),
        webhook_authorization=f"Bearer {secret}",
        connected_at=connection.created_at,
        last_synced_at=connection.last_synced_at,
        last_webhook_at=connection.last_webhook_at,
    )


@router.post(
    "/sdk/users/{user_id}/connections/hevy/sync",
    status_code=status.HTTP_202_ACCEPTED,
)
def sync_hevy_history(user_id: UUID, db: DbSession, auth: SDKAuthDep) -> HevySyncResponse:
    """Queue an idempotent full workout-history sync and establish the live cursor."""
    _authorize_user(auth, user_id)
    if connection_repo.get_active_connection(db, user_id, "hevy") is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hevy is not connected")
    requested_at = datetime.now(timezone.utc)
    _queue_full_sync(user_id, requested_at)
    return HevySyncResponse(status="accepted", requested_at=requested_at)


@router.delete("/sdk/users/{user_id}/connections/hevy", status_code=status.HTTP_204_NO_CONTENT)
def disconnect_hevy(user_id: UUID, db: DbSession, auth: SDKAuthDep) -> Response:
    _authorize_user(auth, user_id)
    connection_repo.disconnect(db, user_id, "hevy")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/hevy/webhooks/{connection_id}")
def receive_hevy_webhook(
    connection_id: UUID,
    payload: HevyWebhookPayload,
    db: DbSession,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, str]:
    """Acknowledge Hevy quickly and fetch the full workout asynchronously."""
    connection = connection_repo.get(db, connection_id)
    if connection is None or connection.provider != "hevy" or connection.status != ConnectionStatus.ACTIVE:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown Hevy connection")
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not verify_webhook_secret(token, connection.webhook_secret_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook authorization")

    connection.last_webhook_at = datetime.now(timezone.utc)
    connection.updated_at = datetime.now(timezone.utc)
    db.add(connection)
    db.commit()
    celery_app.send_task(
        "app.integrations.celery.tasks.hevy_workout_task.ingest_hevy_workout",
        kwargs={"user_id": str(connection.user_id), "workout_id": payload.workout_id},
        queue="webhook_sync",
    )
    return {"status": "accepted"}
