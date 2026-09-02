from sqlalchemy.orm import Session
from starlette.testclient import TestClient

from app.services.sdk_token_service import create_sdk_user_token
from tests.factories import ApiKeyFactory, UserFactory


def _payload(stage: str = "relay_received") -> dict:
    return {
        "event_id": "record_meal_abc123",
        "event_type": "meal.created",
        "stage": stage,
        "source": "bionic-relay",
        "occurred_at": "2026-09-02T09:30:00Z",
        "latency_ms": 1250,
        "detail": {"attempt_count": 1},
    }


def test_records_and_lists_delivery_receipts(client: TestClient, db: Session) -> None:
    user = UserFactory()
    api_key = ApiKeyFactory()
    url = f"/api/v1/sdk/users/{user.id}/delivery-receipts"
    headers = {"X-Open-Wearables-API-Key": api_key.id}

    response = client.post(url, headers=headers, json=_payload())
    assert response.status_code == 202
    assert response.json()["stage"] == "relay_received"

    delivered = _payload("agent_message_delivered")
    delivered["occurred_at"] = "2026-09-02T09:31:00Z"
    response = client.post(url, headers=headers, json=delivered)
    assert response.status_code == 202

    response = client.get(url, headers=headers)
    assert response.status_code == 200
    assert [item["stage"] for item in response.json()] == ["agent_message_delivered", "relay_received"]


def test_receipt_stage_is_idempotent(client: TestClient, db: Session) -> None:
    user = UserFactory()
    api_key = ApiKeyFactory()
    url = f"/api/v1/sdk/users/{user.id}/delivery-receipts"
    headers = {"X-Open-Wearables-API-Key": api_key.id}

    first = client.post(url, headers=headers, json=_payload())
    updated_payload = _payload()
    updated_payload["latency_ms"] = 900
    second = client.post(url, headers=headers, json=updated_payload)

    assert first.status_code == 202
    assert second.status_code == 202
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["latency_ms"] == 900
    listed = client.get(url, headers=headers).json()
    assert len(listed) == 1


def test_sdk_token_is_user_scoped(client: TestClient, db: Session) -> None:
    user = UserFactory()
    other_user = UserFactory()
    token = create_sdk_user_token("bionic", str(user.id))
    headers = {"Authorization": f"Bearer {token}"}

    own = client.get(f"/api/v1/sdk/users/{user.id}/delivery-receipts", headers=headers)
    other = client.get(f"/api/v1/sdk/users/{other_user.id}/delivery-receipts", headers=headers)

    assert own.status_code == 200
    assert other.status_code == 403


def test_rejects_unknown_stage(client: TestClient, db: Session) -> None:
    user = UserFactory()
    api_key = ApiKeyFactory()
    response = client.post(
        f"/api/v1/sdk/users/{user.id}/delivery-receipts",
        headers={"X-Open-Wearables-API-Key": api_key.id},
        json=_payload("made_up"),
    )
    assert response.status_code == 422
