import pytest
from fastapi.testclient import TestClient

from backend.app.core.fixtures import load_generated_manifest
from backend.app.main import app
from backend.app.models import SessionSummary
from backend.app.services.analysis import analysis_store
from backend.app.services.sessions import session_store
from backend.app.services.storage import log_store


@pytest.fixture(autouse=True)
def clear_state() -> None:
    session_store.clear()
    analysis_store.clear()
    log_store.clear_all()


def test_progress_api_returns_empty_state() -> None:
    client = TestClient(app)

    response = client.get("/api/progress")

    assert response.status_code == 200
    body = response.json()
    assert body["session_count"] == 0
    assert body["average_grammar_score"] is None
    assert body["average_pronunciation_score"] is None
    assert body["trend"] == []


def test_progress_api_aggregates_session_summaries() -> None:
    client = TestClient(app)
    first = client.post("/api/sessions", json={"scenario_id": "interview"}).json()
    second = client.post("/api/sessions", json={"scenario_id": "meeting"}).json()
    client.post(
        f"/api/sessions/{first['session']['id']}/turns/text",
        json={"text": "I am working in this field since three years."},
    )
    client.post(
        f"/api/sessions/{second['session']['id']}/turns/text",
        json={"text": "I completed the dashboard update and I am focusing on testing next."},
    )
    item = load_generated_manifest("speechocean762")["items"][0]
    client.post(
        "/api/pronunciation/assess",
        json={"fixture_id": item["id"], "session_id": first["session"]["id"]},
    )
    log_store.save_session_summary(
        SessionSummary(
            session_id=first["session"]["id"],
            grammar_score=80,
            pronunciation_score=75,
            fluency_score=70,
            vocabulary_score=72,
            task_completion_rate=0.5,
        )
    )
    log_store.save_session_summary(
        SessionSummary(
            session_id=second["session"]["id"],
            grammar_score=95,
            pronunciation_score=None,
            fluency_score=76,
            vocabulary_score=78,
            task_completion_rate=0.25,
        )
    )

    response = client.get("/api/progress")

    assert response.status_code == 200
    body = response.json()
    assert body["session_count"] == 2
    assert len(body["trend"]) == 2
    assert body["average_task_completion_rate"] > 0
    assert body["average_grammar_score"] < 100
    assert body["average_pronunciation_score"] is not None
    assert body["trend"][0]["pronunciation_score"] == 75


def test_progress_api_does_not_create_missing_summaries(monkeypatch) -> None:
    client = TestClient(app)
    created = client.post("/api/sessions", json={"scenario_id": "interview"}).json()
    session_id = created["session"]["id"]

    def fail_if_summary_is_created(*_args, **_kwargs):
        raise AssertionError("progress should not create summaries or call providers")

    monkeypatch.setattr("backend.app.services.summary.summary_service.summarize", fail_if_summary_is_created)

    response = client.get("/api/progress")

    assert response.status_code == 200
    body = response.json()
    assert body["session_count"] == 1
    assert body["trend"][0]["session_id"] == session_id
    assert body["trend"][0]["grammar_score"] is None


def test_progress_api_uses_stored_summary_when_present() -> None:
    client = TestClient(app)
    created = client.post("/api/sessions", json={"scenario_id": "interview"}).json()
    session_id = created["session"]["id"]
    log_store.save_session_summary(
        SessionSummary(
            session_id=session_id,
            grammar_score=91,
            pronunciation_score=82,
            fluency_score=73,
            vocabulary_score=64,
            task_completion_rate=0.5,
        )
    )

    response = client.get("/api/progress")

    assert response.status_code == 200
    body = response.json()
    assert body["trend"][0]["grammar_score"] == 91
    assert body["average_pronunciation_score"] == 82
