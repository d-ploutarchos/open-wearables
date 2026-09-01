from uuid import UUID

from app.database import DbSession
from app.models import DataSource, EventRecord, User


class CoachingEventRepository:
    @staticmethod
    def list_user_ids(db: DbSession, user_id: UUID | None = None) -> list[UUID]:
        query = db.query(User.id)
        if user_id is not None:
            query = query.filter(User.id == user_id)
        return [row[0] for row in query.order_by(User.id).all()]

    @staticmethod
    def latest_zone_offset(db: DbSession, user_id: UUID) -> str | None:
        row = (
            db.query(EventRecord.zone_offset)
            .join(DataSource, DataSource.id == EventRecord.data_source_id)
            .filter(DataSource.user_id == user_id, EventRecord.zone_offset.is_not(None))
            .order_by(EventRecord.end_datetime.desc())
            .first()
        )
        return row[0] if row else None
