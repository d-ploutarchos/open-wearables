from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.database import DbSession
from app.schemas.canonical_workout import CanonicalWorkoutResponse
from app.services import ApiKeyDep
from app.services.canonical_workout_service import canonical_workout_service

router = APIRouter()


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
