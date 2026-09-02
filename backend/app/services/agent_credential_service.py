import hashlib
import secrets
from dataclasses import dataclass
from uuid import UUID

from fastapi import HTTPException, status

from app.database import DbSession
from app.models import AgentCredential
from app.repositories.agent_credential_repository import AgentCredentialRepository
from app.schemas.agent_credential import AgentCredentialCreate, AgentCredentialCreateInternal


@dataclass(frozen=True)
class CreatedAgentCredential:
    credential: AgentCredential
    token: str


class AgentCredentialService:
    def __init__(self) -> None:
        self.repository = AgentCredentialRepository()

    @staticmethod
    def _hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def create(self, db: DbSession, user_id: UUID, payload: AgentCredentialCreate) -> CreatedAgentCredential:
        token = f"ow-agent-{secrets.token_urlsafe(32)}"
        credential = self.repository.create(
            db,
            AgentCredentialCreateInternal(
                user_id=user_id,
                name=payload.name,
                token_hash=self._hash_token(token),
                token_prefix=token[:20],
            ),
        )
        return CreatedAgentCredential(credential=credential, token=token)

    def validate(self, db: DbSession, token: str) -> AgentCredential:
        credential = self.repository.get_by_token_hash(db, self._hash_token(token))
        if credential is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid agent credential")
        return credential

    def mark_used(self, db: DbSession, credential: AgentCredential) -> AgentCredential:
        return self.repository.touch(db, credential)

    def list_for_user(self, db: DbSession, user_id: UUID) -> list[AgentCredential]:
        return self.repository.list_for_user(db, user_id)

    def get_for_user(self, db: DbSession, user_id: UUID, credential_id: UUID) -> AgentCredential:
        credential = self.repository.get(db, credential_id, user_id)
        if credential is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent credential not found")
        return credential

    def revoke(self, db: DbSession, user_id: UUID, credential_id: UUID) -> AgentCredential:
        credential = self.get_for_user(db, user_id, credential_id)
        return self.repository.revoke(db, credential)


agent_credential_service = AgentCredentialService()
