from pytest_httpx import HTTPXMock

from app.tools.strength import (
    get_canonical_workout,
    get_coaching_progress,
    get_personal_records,
    get_pr_history,
    get_strength_progress,
    get_training_load,
    list_canonical_workouts,
    list_strength_exercises,
)

USER_ID = "00000000-0000-0000-0000-000000000000"
EXERCISE_ID = "11111111-1111-1111-1111-111111111111"
CANONICAL_ID = "22222222-2222-2222-2222-222222222222"


async def test_get_personal_records_returns_strength_prs(httpx_mock: HTTPXMock) -> None:
    payload = [
        {
            "id": "33333333-3333-3333-3333-333333333333",
            "sport": "strength",
            "record_type": "estimated_one_rep_max",
            "exercise_id": EXERCISE_ID,
            "exercise_name": "Squat (Barbell)",
            "value": "128.333",
            "unit": "kg",
        }
    ]
    httpx_mock.add_response(
        method="GET",
        url=(f"https://api.test.com/api/v1/users/{USER_ID}/performance-records?include_inactive=false&sport=strength"),
        json=payload,
    )

    result = await get_personal_records(USER_ID)

    assert result["total"] == 1
    assert result["records"][0]["record_type"] == "estimated_one_rep_max"


async def test_get_personal_records_filters_running_distance(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url=(
            f"https://api.test.com/api/v1/users/{USER_ID}/performance-records"
            "?include_inactive=false&sport=running&distance_meters=5000"
        ),
        json=[{"sport": "running", "record_type": "fastest_time", "distance_meters": 5000, "value": "1425"}],
    )

    result = await get_personal_records(USER_ID, sport="running", distance_meters=5000)

    assert result["total"] == 1
    assert result["records"][0]["value"] == "1425"


async def test_get_pr_history_passes_filters(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url=(
            f"https://api.test.com/api/v1/users/{USER_ID}/performance-records/history"
            f"?limit=25&exercise_id={EXERCISE_ID}&record_type=max_load"
        ),
        json=[{"change_type": "improved", "value": "120.000"}],
    )

    result = await get_pr_history(USER_ID, exercise_id=EXERCISE_ID, record_type="max_load", limit=25)

    assert result["total"] == 1
    assert result["history"][0]["change_type"] == "improved"


async def test_get_coaching_progress_resolves_exercise_and_passes_thresholds(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url=f"https://api.test.com/api/v1/users/{USER_ID}/strength/exercises?search=Squat",
        json=[{"exercise_id": EXERCISE_ID, "name": "Squat (Barbell)"}],
    )
    httpx_mock.add_response(
        method="GET",
        url=(
            f"https://api.test.com/api/v1/users/{USER_ID}/coaching/progress"
            f"?window_days=56&plateau_attempts=4&exercise_id={EXERCISE_ID}&distance_meters=5000"
        ),
        json={
            "user_id": USER_ID,
            "strength": [{"exercise_name": "Squat (Barbell)", "status": "progressing"}],
            "running": [{"distance_meters": 5000, "status": "maintaining"}],
        },
    )

    result = await get_coaching_progress(
        USER_ID,
        exercise="Squat",
        distance_meters=5000,
        window_days=56,
        plateau_attempts=4,
    )

    assert result["strength"][0]["status"] == "progressing"
    assert result["running"][0]["distance_meters"] == 5000


async def test_get_training_load_passes_windows(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url=(f"https://api.test.com/api/v1/users/{USER_ID}/coaching/training-load?window_days=10&baseline_days=40"),
        json={
            "metrics": [{"metric": "running_distance", "direction": "within_baseline"}],
            "muscle_groups": [],
            "health_scores": [],
        },
    )

    result = await get_training_load(USER_ID, window_days=10, baseline_days=40)

    assert result["metrics"][0]["metric"] == "running_distance"


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


async def test_list_canonical_workouts_passes_history_filters(httpx_mock: HTTPXMock) -> None:
    payload = {
        "data": [{"id": CANONICAL_ID, "name": "Full Body B"}],
        "pagination": {"next_cursor": None, "previous_cursor": None, "has_more": False, "total_count": 1},
    }
    httpx_mock.add_response(
        method="GET",
        url=(
            f"https://api.test.com/api/v1/users/{USER_ID}/canonical-workouts?limit=10"
            "&start_datetime=2026-08-01T00%3A00%3A00Z"
            "&end_datetime=2026-09-01T23%3A59%3A59Z&search=deadlift"
        ),
        json=payload,
    )

    result = await list_canonical_workouts(
        USER_ID,
        start_date="2026-08-01",
        end_date="2026-09-01",
        search="deadlift",
        limit=10,
    )
    assert result == payload


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
