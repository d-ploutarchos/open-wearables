"""MCP tools for detailed, longitudinal strength-training analysis."""

import logging
from decimal import Decimal
from uuid import UUID

from fastmcp import FastMCP

from app.services.api_client import client
from app.services.exceptions import OpenWearablesError

logger = logging.getLogger(__name__)
strength_router = FastMCP(name="Strength Training Tools")


async def _resolve_exercise_id(user_id: str, exercise: str) -> tuple[str | None, dict | None]:
    try:
        UUID(exercise)
        return exercise, None
    except ValueError:
        candidates = await client.list_strength_exercises(user_id, exercise)
        exact = [item for item in candidates if item.get("name", "").casefold() == exercise.casefold()]
        if len(exact) == 1:
            return str(exact[0]["exercise_id"]), None
        if len(candidates) == 1:
            return str(candidates[0]["exercise_id"]), None
        return None, {
            "needs_exercise_selection": True,
            "query": exercise,
            "candidates": candidates,
            "message": "Choose the intended exercise variant and call this tool again with its exercise_id.",
        }


@strength_router.tool
async def get_personal_records(
    user_id: str,
    sport: str = "strength",
    exercise_id: str | None = None,
    distance_meters: int | None = None,
    record_type: str | None = None,
) -> dict:
    """Get current provider-neutral strength or running PRs.

    Strength records include load, exact-rep max, estimated 1RM, and set volume. Running
    records use sport="running" and optionally distance_meters for standard-distance best times.
    """
    try:
        records = await client.list_performance_records(
            user_id,
            sport=sport,
            exercise_id=exercise_id,
            distance_meters=distance_meters,
            record_type=record_type,
        )
        return {"user_id": user_id, "sport": sport, "records": records, "total": len(records)}
    except OpenWearablesError as exc:
        return {"error": str(exc), "records": [], "total": 0}


@strength_router.tool
async def get_pr_history(
    user_id: str,
    sport: str | None = None,
    exercise_id: str | None = None,
    distance_meters: int | None = None,
    record_type: str | None = None,
    limit: int = 100,
) -> dict:
    """Get the chronological ledger of strength or running PR changes."""
    try:
        history = await client.list_performance_record_history(
            user_id,
            sport=sport,
            exercise_id=exercise_id,
            distance_meters=distance_meters,
            record_type=record_type,
            limit=limit,
        )
        return {"user_id": user_id, "history": history, "total": len(history)}
    except OpenWearablesError as exc:
        return {"error": str(exc), "history": [], "total": 0}


@strength_router.tool
async def get_coaching_progress(
    user_id: str,
    exercise: str | None = None,
    distance_meters: int | None = None,
    window_days: int = 42,
    plateau_attempts: int = 3,
) -> dict:
    """Get coach-ready longitudinal strength and running progression signals.

    Returns latest and best performances, baseline change, recent strength-volume direction,
    sessions or attempts since the best result, and conservative new/progressing/maintaining/plateau/inactive
    labels. Pass an exercise name or UUID to focus strength analysis, or a standard running distance.
    """
    try:
        exercise_id = None
        if exercise:
            exercise_id, selection = await _resolve_exercise_id(user_id, exercise)
            if selection is not None:
                return selection
        return await client.get_coaching_progress(
            user_id,
            exercise_id=exercise_id,
            distance_meters=distance_meters,
            window_days=window_days,
            plateau_attempts=plateau_attempts,
        )
    except OpenWearablesError as exc:
        logger.error("API error in get_coaching_progress: %s", exc)
        return {"error": str(exc), "strength": [], "running": []}


@strength_router.tool
async def list_canonical_workouts(
    user_id: str,
    start_date: str | None = None,
    end_date: str | None = None,
    search: str | None = None,
    cursor: str | None = None,
    limit: int = 20,
) -> dict:
    """Search merged workout history by date, workout title, or exercise name.

    Use this for session-level questions such as "show my squat workouts" or
    "what training did I do last week?". Follow pagination.next_cursor when
    pagination.has_more is true.
    """
    try:
        return await client.list_canonical_workouts(
            user_id,
            start_datetime=f"{start_date}T00:00:00Z" if start_date else None,
            end_datetime=f"{end_date}T23:59:59Z" if end_date else None,
            search=search,
            cursor=cursor,
            limit=limit,
        )
    except OpenWearablesError as exc:
        return {"error": str(exc), "data": []}


@strength_router.tool
async def get_canonical_workout(user_id: str, canonical_workout_id: str) -> dict:
    """Get one merged workout with Hevy exercises, Apple physiology, source records, and field provenance."""
    try:
        return await client.get_canonical_workout(user_id, canonical_workout_id)
    except OpenWearablesError as exc:
        return {"error": str(exc), "canonical_workout_id": canonical_workout_id}


@strength_router.tool
async def list_strength_exercises(user_id: str, search: str | None = None) -> dict:
    """List queryable exercise identities, optionally matching a name such as 'squat'."""
    try:
        exercises = await client.list_strength_exercises(user_id, search)
        return {"user_id": user_id, "search": search, "exercises": exercises, "total": len(exercises)}
    except OpenWearablesError as exc:
        return {"error": str(exc), "exercises": [], "total": 0}


@strength_router.tool
async def get_strength_progress(
    user_id: str,
    exercise: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    """Get set-derived history and progress for an exercise name or stable exercise UUID.

    Use this for questions about load, volume, repetitions, training frequency, or estimated
    one-rep-max development. Different exercise variants remain separate identities.
    """
    try:
        exercise_id, selection = await _resolve_exercise_id(user_id, exercise)
        if selection is not None or exercise_id is None:
            return selection or {"error": "Exercise could not be resolved"}

        history = await client.get_strength_exercise_history(
            user_id,
            exercise_id,
            f"{start_date}T00:00:00Z" if start_date else None,
            f"{end_date}T23:59:59Z" if end_date else None,
        )
        points = history.get("history", [])
        first = points[0] if points else None
        latest = points[-1] if points else None

        change: float | None = None
        if first and latest:
            first_e1rm = first.get("estimated_one_rep_max_kg")
            latest_e1rm = latest.get("estimated_one_rep_max_kg")
            if first_e1rm is not None and latest_e1rm is not None:
                change = float(Decimal(str(latest_e1rm)) - Decimal(str(first_e1rm)))

        history["summary"] = {
            "sessions": len(points),
            "first_session": first,
            "latest_session": latest,
            "estimated_one_rep_max_change_kg": change,
            "estimated_one_rep_max_formula": "Epley: weight × (1 + reps / 30)",
        }
        return history
    except OpenWearablesError as exc:
        logger.error("API error in get_strength_progress: %s", exc)
        return {"error": str(exc)}
