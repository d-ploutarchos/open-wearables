from decimal import Decimal

from app.schemas.providers.hevy import HevyWorkout, HevyWorkoutEventsPage
from app.services.providers.hevy.strength_storage import normalize_exercise_name, total_volume

WORKOUT = {
    "id": "b459cba5-cd6d-463c-abd6-54f8eafcadcb",
    "title": "Leg day",
    "start_time": "2026-08-31T10:00:00Z",
    "end_time": "2026-08-31T11:00:00Z",
    "exercises": [
        {
            "index": 0,
            "title": "Squat (Barbell)",
            "notes": "Controlled eccentric",
            "exercise_template_id": "05293BCA",
            "supersets_id": 0,
            "sets": [
                {"index": 0, "type": "warmup", "weight_kg": 60, "reps": 5},
                {"index": 1, "type": "normal", "weight_kg": 100, "reps": 5, "rpe": 8.5},
                {"index": 2, "type": "normal", "weight_kg": 105, "reps": 3, "rpe": 9},
            ],
        }
    ],
}


def test_hevy_workout_preserves_detailed_sets_and_numeric_superset() -> None:
    workout = HevyWorkout.model_validate(WORKOUT)
    assert workout.exercises[0].supersets_id == 0
    assert workout.exercises[0].sets[1].rpe == Decimal("8.5")
    assert total_volume(workout) == Decimal("815")


def test_hevy_event_page_parses_updates_and_deletes() -> None:
    page = HevyWorkoutEventsPage.model_validate(
        {
            "page": 1,
            "page_count": 1,
            "events": [
                {"type": "updated", "workout": WORKOUT},
                {"type": "deleted", "id": WORKOUT["id"], "deleted_at": "2026-09-01T10:00:00Z"},
            ],
        }
    )
    assert page.events[0].workout is not None
    assert page.events[1].id == WORKOUT["id"]


def test_exercise_name_normalization_keeps_variants_queryable() -> None:
    assert normalize_exercise_name("Squat (Barbell)") == "squat barbell"
