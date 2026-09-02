from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.database import DbSession
from app.schemas.agent_credential import (
    AgentCredentialContact,
    AgentCredentialCreate,
    AgentCredentialCreated,
    AgentCredentialRead,
    AgentWebhookConfigure,
    AgentWebhookRead,
    AgentWebhookTestResult,
)
from app.services.agent_credential_service import agent_credential_service
from app.services.agent_webhook_service import agent_webhook_service
from app.utils.auth import SDKAuthDep

router = APIRouter()


def _authorize_user(user_id: UUID, auth: SDKAuthDep) -> None:
    if auth.auth_type == "sdk_token" and auth.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Token does not match user_id")


@router.get("/sdk/users/{user_id}/agent-credentials")
def list_agent_credentials(user_id: UUID, db: DbSession, auth: SDKAuthDep) -> list[AgentCredentialRead]:
    """List user-scoped agent credentials without exposing their secret values."""
    _authorize_user(user_id, auth)
    return [
        AgentCredentialRead.model_validate(credential)
        for credential in agent_credential_service.list_for_user(db, user_id)
    ]


@router.post("/sdk/users/{user_id}/agent-credentials", status_code=status.HTTP_201_CREATED)
def create_agent_credential(
    user_id: UUID,
    body: AgentCredentialCreate,
    db: DbSession,
    auth: SDKAuthDep,
) -> AgentCredentialCreated:
    """Create a read-only credential; its complete token is returned once."""
    _authorize_user(user_id, auth)
    created = agent_credential_service.create(db, user_id, body)
    return AgentCredentialCreated(
        **AgentCredentialRead.model_validate(created.credential).model_dump(),
        token=created.token,
    )


@router.delete(
    "/sdk/users/{user_id}/agent-credentials/{credential_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def revoke_agent_credential(
    user_id: UUID,
    credential_id: UUID,
    db: DbSession,
    auth: SDKAuthDep,
) -> None:
    """Revoke an agent credential immediately."""
    _authorize_user(user_id, auth)
    credential = agent_credential_service.get_for_user(db, user_id, credential_id)
    # Revoke database access before making the external Svix call so a failing
    # webhook cleanup can never leave the read credential usable.
    agent_credential_service.revoke(db, user_id, credential_id)
    if credential.webhook_endpoint_id:
        application = agent_webhook_service.application_for_sdk(db, auth.app_id)
        agent_webhook_service.delete(db, credential, application)


@router.get("/sdk/users/{user_id}/agent-credentials/{credential_id}/contact")
def get_agent_contact(
    user_id: UUID,
    credential_id: UUID,
    db: DbSession,
    auth: SDKAuthDep,
) -> AgentCredentialContact:
    """Check whether this agent credential has accessed health data recently."""
    _authorize_user(user_id, auth)
    credential = agent_credential_service.get_for_user(db, user_id, credential_id)
    checked_at = datetime.now(timezone.utc)
    return AgentCredentialContact(
        credential_id=credential.id,
        checked_at=checked_at,
        last_used_at=credential.last_used_at,
        connected=credential.revoked_at is None
        and credential.last_used_at is not None
        and checked_at - credential.last_used_at <= timedelta(minutes=15),
    )


@router.put("/sdk/users/{user_id}/agent-credentials/{credential_id}/webhook")
def configure_agent_webhook(
    user_id: UUID,
    credential_id: UUID,
    body: AgentWebhookConfigure,
    db: DbSession,
    auth: SDKAuthDep,
) -> AgentWebhookRead:
    """Create or update a user-filtered outgoing webhook for an agent."""
    _authorize_user(user_id, auth)
    credential = agent_credential_service.get_for_user(db, user_id, credential_id)
    application = agent_webhook_service.application_for_sdk(db, auth.app_id)
    return agent_webhook_service.configure(db, credential, application, body)


@router.post("/sdk/users/{user_id}/agent-credentials/{credential_id}/webhook/test")
def test_agent_webhook(
    user_id: UUID,
    credential_id: UUID,
    db: DbSession,
    auth: SDKAuthDep,
) -> AgentWebhookTestResult:
    """Send a signed example event to the configured agent webhook."""
    _authorize_user(user_id, auth)
    credential = agent_credential_service.get_for_user(db, user_id, credential_id)
    application = agent_webhook_service.application_for_sdk(db, auth.app_id)
    return agent_webhook_service.test(credential, application)


@router.delete(
    "/sdk/users/{user_id}/agent-credentials/{credential_id}/webhook",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_agent_webhook(
    user_id: UUID,
    credential_id: UUID,
    db: DbSession,
    auth: SDKAuthDep,
) -> None:
    """Delete the outgoing webhook while retaining MCP access."""
    _authorize_user(user_id, auth)
    credential = agent_credential_service.get_for_user(db, user_id, credential_id)
    application = agent_webhook_service.application_for_sdk(db, auth.app_id)
    agent_webhook_service.delete(db, credential, application)
