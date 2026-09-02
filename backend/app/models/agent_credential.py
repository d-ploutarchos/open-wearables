from datetime import datetime
from uuid import UUID

from sqlalchemy import Index, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import BaseDbModel
from app.mappings import FKUser, PrimaryKey, str_32, str_64, str_100


class AgentCredential(BaseDbModel):
    """Revocable, read-only API credential scoped to one health-data owner."""

    __tablename__ = "agent_credential"
    __table_args__ = (
        Index("uq_agent_credential_token_hash", "token_hash", unique=True),
        Index("ix_agent_credential_user_active", "user_id", "revoked_at"),
    )

    id: Mapped[PrimaryKey[UUID]]
    user_id: Mapped[FKUser]
    name: Mapped[str_100]
    token_hash: Mapped[str_64]
    token_prefix: Mapped[str_32]
    webhook_endpoint_id: Mapped[str_64 | None]
    webhook_url: Mapped[str | None] = mapped_column(Text)
    last_used_at: Mapped[datetime | None]
    revoked_at: Mapped[datetime | None]
