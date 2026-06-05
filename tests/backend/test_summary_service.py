import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services.scenarios import get_scenario
from backend.app.services.sessions import session_store
from backend.app.services.summary import summary_service


@pytest.fixture(autouse=True)
def clear_session_store() -> None:
    session_store.clear()


def test_summary_service_returns_partial_summary_without_pronunciation() -> None:
    scenario = get_scenario("interview")
    assert scenario is not None
    session = session_store.create(scenario)
    session.add_turn(
        speaker="user",
        text="I am working in this field since three years.",
    )

    summary = summary_service.summarize(session=session, scenario=scenario)

    assert summary.session_id == session.id
    assert summary.pronunciation_score is None
    assert summary.grammar_score == 70
    assert summary.task_completion_rate == 0.25
    assert "preposition" in summary.top_issues
    assert summary.next_drills


def test_summary_service_uses_target_expressions_when_no_errors() -> None:
    scenario = get_scenario("interview")
    assert scenario is not None
    session = session_store.create(scenario)
    session.add_turn(
        speaker="user",
        text="I have worked on backend systems for three years.",
    )

    summary = summary_service.summarize(session=session, scenario=scenario)

    assert summary.grammar_score == 100
    assert summary.top_issues == []
    assert summary.next_drills[0].startswith("Practice using:")


def test_summary_api_returns_session_summary() -> None:
    client = TestClient(app)
    created = client.post("/api/sessions", json={"scenario_id": "interview"}).json()
    session_id = created["session"]["id"]
    client.post(
        f"/api/sessions/{session_id}/turns/text",
        json={"text": "I am working in this field since three years."},
    )

    response = client.get(f"/api/sessions/{session_id}/summary")

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == session_id
    assert body["pronunciation_score"] is None
    assert body["top_issues"]


def test_summary_api_rejects_unknown_session() -> None:
    client = TestClient(app)

    response = client.get("/api/sessions/not-found/summary")

    assert response.status_code == 404
    assert response.json()["detail"] == "Unknown session"
