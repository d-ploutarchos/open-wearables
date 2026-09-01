from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from app.database import DbSession
from app.schemas.canonical_workout import CanonicalWorkoutListResponse, CanonicalWorkoutResponse
from app.services import ApiKeyDep
from app.services.canonical_workout_service import canonical_workout_service

router = APIRouter()


@router.get("/users/{user_id}/canonical-workouts")
def list_canonical_workouts(
    user_id: UUID,
    db: DbSession,
    _api_key: ApiKeyDep,
    start_datetime: datetime | None = None,
    end_datetime: datetime | None = None,
    search: Annotated[str | None, Query(max_length=100)] = None,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> CanonicalWorkoutListResponse:
    """List merged workout history, optionally matching workout or exercise names."""
    return canonical_workout_service.list_responses(
        db,
        user_id,
        start_datetime=start_datetime,
        end_datetime=end_datetime,
        search=search,
        cursor=cursor,
        limit=limit,
    )


@router.get("/users/{user_id}/canonical-workouts/{canonical_workout_id}")
def get_canonical_workout(
    user_id: UUID,
    canonical_workout_id: UUID,
    db: DbSession,
    _api_key: ApiKeyDep,
) -> CanonicalWorkoutResponse:
    """Return one physical workout merged from all correlated provider records."""
    response = canonical_workout_service.get_response(db, canonical_workout_id, user_id)
    if response is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Canonical workout not found")
    return response
