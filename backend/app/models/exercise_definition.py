from uuid import UUID

from sqlalchemy import Boolean, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.database import BaseDbModel
from app.mappings import FKUser, PrimaryKey, str_64, str_100, str_255
from app.schemas.enums import ProviderName


class ExerciseDefinition(BaseDbModel):
    """Stable, user-scoped identity for an exercise supplied by a provider."""

    __tablename__ = "exercise_definition"
    __table_args__ = (
        Index(
            "uq_exercise_definition_provider_identity",
            "user_id",
            "provider",
            "provider_exercise_id",
            unique=True,
        ),
        Index("ix_exercise_definition_user_normalized_name", "user_id", "normalized_name"),
    )

    id: Mapped[PrimaryKey[UUID]]
    user_id: Mapped[FKUser]
    provider: Mapped[ProviderName]
    provider_exercise_id: Mapped[str_100]
    name: Mapped[str_255]
    normalized_name: Mapped[str_255]
    equipment: Mapped[str_64 | None]
    primary_muscle_group: Mapped[str_64 | None]
    is_custom: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
