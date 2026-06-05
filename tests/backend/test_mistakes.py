import pytest
from fastapi.testclient import TestClient

from backend.app.core.fixtures import load_generated_manifest, load_text_fixture
from backend.app.main import app
from backend.app.services.storage import log_store


@pytest.fixture(autouse=True)
def clear_log_store() -> None:
    log_store.clear_all()


def test_grammar_check_generates_and_merges_mistakes() -> None:
    client = TestClient(app)
    item = load_text_fixture("grammar_expression_errors")["items"][0]
    payload = {
        "scenario_id": item["scenario_id"],
        "user_text": item["original_text"],
        "conversation_context": [],
    }

    first = client.post("/api/grammar/check", json=payload)
    second = client.post("/api/grammar/check", json=payload)
    mistakes = client.get("/api/mistakes").json()["mistakes"]

    assert first.status_code == 200
    assert second.status_code == 200
    grammar_mistakes = [mistake for mistake in mistakes if mistake["type"] == "grammar"]
    assert len(grammar_mistakes) == 1
    assert grammar_mistakes[0]["wrong"] == item["error_span"]


def test_pronunciation_assessment_generates_pronunciation_mistakes() -> None:
    client = TestClient(app)
    item = load_generated_manifest("speechocean762")["items"][0]

    response = client.post("/api/pronunciation/assess", json={"fixture_id": item["id"]})
    mistakes = client.get("/api/mistakes").json()["mistakes"]

    assert response.status_code == 200
    pronunciation = [mistake for mistake in mistakes if mistake["type"] == "pronunciation"]
    assert pronunciation
    assert {mistake["word"].lower() for mistake in pronunciation} >= {"theme"}


def test_review_mistake_updates_count_and_mastery() -> None:
    client = TestClient(app)
    item = load_text_fixture("grammar_expression_errors")["items"][0]
    client.post(
        "/api/grammar/check",
        json={
            "scenario_id": item["scenario_id"],
            "user_text": item["original_text"],
            "conversation_context": [],
        },
    )
    mistake = client.get("/api/mistakes").json()["mistakes"][0]

    response = client.post(f"/api/mistakes/{mistake['id']}/review")

    assert response.status_code == 200
    reviewed = response.json()
    assert reviewed["review_count"] == mistake["review_count"] + 1
    assert reviewed["mastery"] > mistake["mastery"]


def test_review_mistake_rejects_unknown_id() -> None:
    client = TestClient(app)

    response = client.post("/api/mistakes/not-found/review")

    assert response.status_code == 404
    assert response.json()["detail"] == "Unknown mistake"
