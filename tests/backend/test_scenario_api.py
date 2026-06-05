import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services.sessions import session_store


@pytest.fixture(autouse=True)
def clear_session_store() -> None:
    session_store.clear()


def test_list_scenarios_returns_fixture_config() -> None:
    client = TestClient(app)

    response = client.get("/api/scenarios")

    assert response.status_code == 200
    body = response.json()
    assert [scenario["id"] for scenario in body["scenarios"]] == [
        "interview",
        "restaurant_ordering",
        "meeting",
    ]
    assert body["scenarios"][0]["opening_line"]


def test_create_session_returns_opening_turn_and_goals() -> None:
    client = TestClient(app)

    response = client.post("/api/sessions", json={"scenario_id": "interview"})

    assert response.status_code == 201
    body = response.json()
    assert body["session"]["scenario_id"] == "interview"
    assert body["session"]["status"] == "active"
    assert body["opening_line"] == body["session"]["turns"][0]["text"]
    assert body["session"]["turns"][0]["speaker"] == "ai"
    assert body["conversation_goals"]
    assert body["target_expressions"]


def test_create_session_rejects_unknown_scenario() -> None:
    client = TestClient(app)

    response = client.post("/api/sessions", json={"scenario_id": "unknown"})

    assert response.status_code == 404
    assert response.json()["detail"] == "Unknown scenario"


def test_end_session_transitions_status() -> None:
    client = TestClient(app)
    created = client.post("/api/sessions", json={"scenario_id": "meeting"}).json()
    session_id = created["session"]["id"]

    response = client.post(f"/api/sessions/{session_id}/end")

    assert response.status_code == 200
    body = response.json()
    assert body["session"]["id"] == session_id
    assert body["session"]["status"] == "ended"
    assert body["session"]["ended_at"] is not None


def test_end_session_rejects_unknown_session() -> None:
    client = TestClient(app)

    response = client.post("/api/sessions/not-found/end")

    assert response.status_code == 404
    assert response.json()["detail"] == "Unknown session"
