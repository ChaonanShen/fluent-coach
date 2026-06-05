import pytest
from fastapi.testclient import TestClient

from backend.app.core.fixtures import load_generated_manifest
from backend.app.main import app
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

    response = client.get("/api/progress")

    assert response.status_code == 200
    body = response.json()
    assert body["session_count"] == 2
    assert len(body["trend"]) == 2
    assert body["average_task_completion_rate"] > 0
    assert body["average_grammar_score"] < 100
    assert body["average_pronunciation_score"] is not None
    assert body["trend"][0]["pronunciation_score"] is not None
