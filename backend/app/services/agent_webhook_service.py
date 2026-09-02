from fastapi import HTTPException, status

from app.database import DbSession
from app.models import AgentCredential, Application
from app.schemas.agent_credential import (
    AgentWebhookConfigure,
    AgentWebhookRead,
    AgentWebhookTestResult,
)
from app.schemas.webhooks.event_types import WebhookEventType
from app.services.agent_credential_service import agent_credential_service
from app.services.application_service import application_service
from app.services.developer_service import developer_service
from app.services.outgoing_webhooks import svix as svix_service


class AgentWebhookService:
    def application_for_sdk(self, db: DbSession, app_id: str | None) -> Application:
        if app_id is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="SDK application is required")
        application = application_service.get_by_app_id(db, app_id)
        if application is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SDK application not found")
        return application

    def configure(
        self,
        db: DbSession,
        credential: AgentCredential,
        application: Application,
        payload: AgentWebhookConfigure,
    ) -> AgentWebhookRead:
        if not svix_service.is_enabled():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Outgoing webhooks are disabled",
            )
        allowed_event_types = {event_type.value for event_type in WebhookEventType}
        unknown = sorted(set(payload.event_types) - allowed_event_types)
        if unknown:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unsupported webhook event types: {', '.join(unknown)}",
            )
        developer = developer_service.get(db, application.developer_id, raise_404=True)
        assert developer is not None
        svix_app_id = svix_service.ensure_application(str(developer.id), developer.email)
        url = str(payload.url)
        if credential.webhook_endpoint_id:
            endpoint = svix_service.patch_endpoint(
                svix_app_id,
                credential.webhook_endpoint_id,
                url=url,
                description=f"Bionic agent: {credential.name}",
                filter_types=payload.event_types,
                user_id=credential.user_id,
            )
        else:
            endpoint = svix_service.create_endpoint(
                svix_app_id,
                url=url,
                description=f"Bionic agent: {credential.name}",
                filter_types=payload.event_types,
                user_id=credential.user_id,
            )
        credential = agent_credential_service.repository.set_webhook(db, credential, endpoint.id, endpoint.url)
        secret = svix_service.get_endpoint_secret(svix_app_id, endpoint.id)
        return AgentWebhookRead(
            endpoint_id=endpoint.id,
            url=endpoint.url,
            event_types=endpoint.filter_types or payload.event_types,
            signing_secret=secret,
        )

    def test(self, credential: AgentCredential, application: Application) -> AgentWebhookTestResult:
        if not credential.webhook_endpoint_id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Configure the agent webhook first")
        message = svix_service.send_test_message(
            str(application.developer_id),
            credential.webhook_endpoint_id,
            WebhookEventType.WORKOUT_CREATED,
        )
        if message is None:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Could not send webhook test")
        return AgentWebhookTestResult(message_id=message.id, status="sent")

    def delete(self, db: DbSession, credential: AgentCredential, application: Application) -> None:
        if credential.webhook_endpoint_id:
            svix_service.delete_endpoint(str(application.developer_id), credential.webhook_endpoint_id)
            agent_credential_service.repository.set_webhook(db, credential, None, None)


agent_webhook_service = AgentWebhookService()
