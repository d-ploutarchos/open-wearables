from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import AgentCredential
from app.schemas.agent_credential import AgentCredentialCreateInternal


class AgentCredentialRepository:
    def create(self, db: Session, creator: AgentCredentialCreateInternal) -> AgentCredential:
        credential = AgentCredential(**creator.model_dump())
        db.add(credential)
        db.commit()
        db.refresh(credential)
        return credential

    def get(self, db: Session, credential_id: UUID, user_id: UUID | None = None) -> AgentCredential | None:
        query = db.query(AgentCredential).filter(AgentCredential.id == credential_id)
        if user_id is not None:
            query = query.filter(AgentCredential.user_id == user_id)
        return query.one_or_none()

    def get_by_token_hash(self, db: Session, token_hash: str) -> AgentCredential | None:
        return (
            db.query(AgentCredential)
            .filter(AgentCredential.token_hash == token_hash, AgentCredential.revoked_at.is_(None))
            .one_or_none()
        )

    def list_for_user(self, db: Session, user_id: UUID) -> list[AgentCredential]:
        return (
            db.query(AgentCredential)
            .filter(AgentCredential.user_id == user_id)
            .order_by(AgentCredential.created_at.desc())
            .all()
        )

    def touch(self, db: Session, credential: AgentCredential) -> AgentCredential:
        credential.last_used_at = datetime.now(timezone.utc)
        db.add(credential)
        db.commit()
        db.refresh(credential)
        return credential

    def revoke(self, db: Session, credential: AgentCredential) -> AgentCredential:
        credential.revoked_at = datetime.now(timezone.utc)
        db.add(credential)
        db.commit()
        db.refresh(credential)
        return credential

    def set_webhook(
        self,
        db: Session,
        credential: AgentCredential,
        endpoint_id: str | None,
        url: str | None,
    ) -> AgentCredential:
        credential.webhook_endpoint_id = endpoint_id
        credential.webhook_url = url
        db.add(credential)
        db.commit()
        db.refresh(credential)
        return credential
