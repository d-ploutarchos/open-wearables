from sqlalchemy.orm import Session
from starlette.testclient import TestClient

from app.services.sdk_token_service import create_sdk_user_token
from tests.factories import UserFactory


def _sdk_headers(user_id: str) -> dict[str, str]:
    token = create_sdk_user_token("bionic", user_id)
    return {"Authorization": f"Bearer {token}"}


def test_creates_one_time_user_scoped_read_credential(client: TestClient, db: Session) -> None:
    user = UserFactory()
    other_user = UserFactory()
    url = f"/api/v1/sdk/users/{user.id}/agent-credentials"

    created = client.post(url, headers=_sdk_headers(str(user.id)), json={"name": "Hermes"})
    assert created.status_code == 201
    body = created.json()
    assert body["token"].startswith("ow-agent-")
    assert body["name"] == "Hermes"

    listed = client.get(url, headers=_sdk_headers(str(user.id)))
    assert listed.status_code == 200
    assert listed.json()[0]["token_prefix"] == body["token_prefix"]
    assert "token" not in listed.json()[0]

    agent_headers = {"X-Open-Wearables-API-Key": body["token"]}
    own_user = client.get(f"/api/v1/users/{user.id}", headers=agent_headers)
    other = client.get(f"/api/v1/users/{other_user.id}", headers=agent_headers)
    mutation = client.delete(
        f"/api/v1/users/{user.id}/events/workouts/00000000-0000-0000-0000-000000000000",
        headers=agent_headers,
    )
    unscoped = client.get("/api/v1/users", headers=agent_headers)

    assert own_user.status_code == 200
    assert other.status_code == 403
    assert mutation.status_code == 403
    assert unscoped.status_code == 403

    contact = client.get(
        f"{url}/{body['id']}/contact",
        headers=_sdk_headers(str(user.id)),
    )
    assert contact.status_code == 200
    assert contact.json()["connected"] is True
    assert contact.json()["last_used_at"] is not None


def test_revocation_invalidates_agent_credential(client: TestClient, db: Session) -> None:
    user = UserFactory()
    url = f"/api/v1/sdk/users/{user.id}/agent-credentials"
    sdk_headers = _sdk_headers(str(user.id))
    created = client.post(url, headers=sdk_headers, json={"name": "OpenClaw"}).json()
    agent_headers = {"X-Open-Wearables-API-Key": created["token"]}

    revoked = client.delete(f"{url}/{created['id']}", headers=sdk_headers)
    after_revoke = client.get(f"/api/v1/users/{user.id}", headers=agent_headers)

    assert revoked.status_code == 204
    assert after_revoke.status_code == 401


def test_sdk_token_cannot_manage_another_users_credentials(client: TestClient, db: Session) -> None:
    user = UserFactory()
    other_user = UserFactory()
    response = client.post(
        f"/api/v1/sdk/users/{other_user.id}/agent-credentials",
        headers=_sdk_headers(str(user.id)),
        json={"name": "Wrong user"},
    )
    assert response.status_code == 403
