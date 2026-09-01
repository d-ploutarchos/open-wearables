from pytest_httpx import HTTPXMock

from app.tools.strength import get_canonical_workout, get_strength_progress, list_strength_exercises

USER_ID = "00000000-0000-0000-0000-000000000000"
EXERCISE_ID = "11111111-1111-1111-1111-111111111111"
CANONICAL_ID = "22222222-2222-2222-2222-222222222222"


async def test_get_canonical_workout_returns_merged_payload(httpx_mock: HTTPXMock) -> None:
    payload = {
        "id": CANONICAL_ID,
        "user_id": USER_ID,
        "type": "strength_training",
        "name": "Full Body B",
        "exercises": [{"title": "Romanian Deadlift"}],
        "calories_kcal": 201.693,
        "sources": [{"provider": "hevy"}, {"provider": "apple"}],
        "provenance": {"exercises": "hevy", "calories_kcal": "apple"},
    }
    httpx_mock.add_response(
        method="GET",
        url=f"https://api.test.com/api/v1/users/{USER_ID}/canonical-workouts/{CANONICAL_ID}",
        json=payload,
    )

    assert await get_canonical_workout(USER_ID, CANONICAL_ID) == payload


async def test_list_strength_exercises_passes_search(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url=f"https://api.test.com/api/v1/users/{USER_ID}/strength/exercises?search=squat",
        json=[
            {
                "exercise_id": EXERCISE_ID,
                "name": "Squat (Barbell)",
                "provider": "hevy",
                "provider_exercise_id": "05293BCA",
                "workout_count": 4,
                "last_performed_at": "2026-08-31T10:00:00Z",
            }
        ],
    )
    result = await list_strength_exercises(USER_ID, "squat")
    assert result["total"] == 1
    assert result["exercises"][0]["exercise_id"] == EXERCISE_ID


async def test_get_strength_progress_resolves_name_and_summarizes_change(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url=f"https://api.test.com/api/v1/users/{USER_ID}/strength/exercises?search=Squat+%28Barbell%29",
        json=[
            {
                "exercise_id": EXERCISE_ID,
                "name": "Squat (Barbell)",
                "provider": "hevy",
                "provider_exercise_id": "05293BCA",
                "workout_count": 2,
            }
        ],
    )
    httpx_mock.add_response(
        method="GET",
        url=(
            f"https://api.test.com/api/v1/users/{USER_ID}/strength/exercises/{EXERCISE_ID}/history"
            "?start_datetime=2026-01-01T00%3A00%3A00Z&end_datetime=2026-08-31T23%3A59%3A59Z"
        ),
        json={
            "exercise_id": EXERCISE_ID,
            "exercise_name": "Squat (Barbell)",
            "provider_exercise_id": "05293BCA",
            "history": [
                {"estimated_one_rep_max_kg": 100, "performed_at": "2026-01-10T10:00:00Z"},
                {"estimated_one_rep_max_kg": 112.5, "performed_at": "2026-08-31T10:00:00Z"},
            ],
        },
    )
    result = await get_strength_progress(
        USER_ID,
        "Squat (Barbell)",
        start_date="2026-01-01",
        end_date="2026-08-31",
    )
    assert result["summary"]["sessions"] == 2
    assert result["summary"]["estimated_one_rep_max_change_kg"] == 12.5
