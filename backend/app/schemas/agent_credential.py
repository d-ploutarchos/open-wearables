from datetime import datetime, timezone
from uuid import UUID, uuid4

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field


class AgentCredentialCreate(BaseModel):
    name: str = Field(default="My AI coach", min_length=1, max_length=100)


class AgentCredentialCreateInternal(AgentCredentialCreate):
    id: UUID = Field(default_factory=uuid4)
    user_id: UUID
    token_hash: str
    token_prefix: str
    webhook_endpoint_id: str | None = None
    webhook_url: str | None = None
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None


class AgentCredentialRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    name: str
    token_prefix: str
    webhook_endpoint_id: str | None
    webhook_url: str | None
    last_used_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime


class AgentCredentialCreated(AgentCredentialRead):
    token: str


class AgentCredentialContact(BaseModel):
    credential_id: UUID
    checked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_used_at: datetime | None
    connected: bool


class AgentWebhookConfigure(BaseModel):
    url: AnyHttpUrl
    event_types: list[str] = Field(
        default_factory=lambda: [
            "workout.created",
            "sleep.created",
            "nutrition.created",
            "coaching.weekly_review.created",
            "coaching.load_alert.created",
        ],
        min_length=1,
        max_length=20,
    )


class AgentWebhookRead(BaseModel):
    endpoint_id: str
    url: str
    event_types: list[str]
    signing_secret: str | None = None


class AgentWebhookTestResult(BaseModel):
    message_id: str
    status: str
