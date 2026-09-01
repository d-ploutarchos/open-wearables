from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from app.database import DbSession
from app.schemas.performance_records import PerformanceRecordHistoryResponse, PerformanceRecordResponse
from app.services import ApiKeyDep
from app.services.performance_record_service import performance_record_service

router = APIRouter()


@router.get("/users/{user_id}/performance-records")
def list_performance_records(
    user_id: UUID,
    db: DbSession,
    _api_key: ApiKeyDep,
    sport: Annotated[str | None, Query(max_length=32)] = None,
    exercise_id: UUID | None = None,
    record_type: Annotated[str | None, Query(max_length=32)] = None,
    include_inactive: bool = False,
) -> list[PerformanceRecordResponse]:
    """List the user's current provider-neutral athletic records."""
    return performance_record_service.list_records(
        db,
        user_id,
        sport=sport,
        exercise_definition_id=exercise_id,
        record_type=record_type,
        include_inactive=include_inactive,
    )


@router.get("/users/{user_id}/performance-records/history")
def list_performance_record_history(
    user_id: UUID,
    db: DbSession,
    _api_key: ApiKeyDep,
    exercise_id: UUID | None = None,
    record_type: Annotated[str | None, Query(max_length=32)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[PerformanceRecordHistoryResponse]:
    """List record-setting, correction, restoration, and revocation history."""
    return performance_record_service.list_history(
        db,
        user_id,
        exercise_definition_id=exercise_id,
        record_type=record_type,
        limit=limit,
    )
