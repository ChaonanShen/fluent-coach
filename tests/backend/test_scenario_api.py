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
    assert body["session"]["title"].startswith("Job Interview - ")
    assert body["session"]["title_source"] == "fallback"
    assert body["session"]["scenario_name_snapshot"] == "Job Interview"
    assert body["conversation_goals"]
    assert body["target_expressions"]


def test_create_session_rejects_unknown_scenario() -> None:
    client = TestClient(app)

    response = client.post("/api/sessions", json={"scenario_id": "unknown"})

    assert response.status_code == 404
    assert response.json()["detail"] == "Unknown scenario"


def test_create_custom_session_keeps_scenario_for_follow_up_calls() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/sessions",
        json={"scenario_id": "custom", "custom_topic": "airport check-in"},
    )

    assert response.status_code == 201
    body = response.json()
    session_id = body["session"]["id"]
    assert body["session"]["scenario_id"].startswith("custom_")
    assert body["session"]["custom_scenario"]["user_role"] == "Learner practicing: airport check-in"
    assert body["session"]["custom_prompt"] == "airport check-in"
    assert "airport check-in" in body["opening_line"]

    turn_response = client.post(
        f"/api/sessions/{session_id}/turns/text",
        json={"text": "I need to check in for my flight to Seattle."},
    )
    assert turn_response.status_code == 200
    assert turn_response.json()["ai_turn"]["speaker"] == "ai"

    summary_response = client.get(f"/api/sessions/{session_id}/summary")
    assert summary_response.status_code == 200
    assert summary_response.json()["task_completion_rate"] > 0


def test_create_custom_session_accepts_prompt_and_name() -> None:
    client = TestClient(app)
    prompt = (
        "I want to practice checking in at a hotel. The AI should be a front desk clerk. "
        "Make it B1 level and include a reservation problem."
    )

    response = client.post(
        "/api/sessions",
        json={
            "scenario_id": "custom",
            "custom_prompt": prompt,
            "custom_name": "Hotel check-in",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["scenario"]["name"] == "Hotel check-in"
    assert body["session"]["custom_prompt"] == prompt
    assert body["session"]["custom_scenario"]["user_role"] == "Learner practicing: Hotel check-in"
    assert body["opening_line"].startswith("Let's practice Hotel check-in.")
    assert "reservation problem" in body["conversation_goals"][0]


def test_create_custom_session_requires_prompt_or_topic() -> None:
    client = TestClient(app)

    response = client.post("/api/sessions", json={"scenario_id": "custom"})

    assert response.status_code == 422


def test_update_session_title_uses_manual_source_and_survives_end() -> None:
    client = TestClient(app)
    created = client.post("/api/sessions", json={"scenario_id": "meeting"}).json()
    session_id = created["session"]["id"]

    rename_response = client.patch(
        f"/api/sessions/{session_id}/title",
        json={"title": "  Weekly sync blockers  "},
    )
    ended_response = client.post(f"/api/sessions/{session_id}/end")

    assert rename_response.status_code == 200
    renamed = rename_response.json()
    assert renamed["title"] == "Weekly sync blockers"
    assert renamed["title_source"] == "manual"
    assert ended_response.status_code == 200
    ended = ended_response.json()["session"]
    assert ended["title"] == "Weekly sync blockers"
    assert ended["title_source"] == "manual"


def test_update_session_title_rejects_unknown_session() -> None:
    client = TestClient(app)

    response = client.patch("/api/sessions/not-found/title", json={"title": "Interview practice"})

    assert response.status_code == 404
    assert response.json()["detail"] == "Unknown session"


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
