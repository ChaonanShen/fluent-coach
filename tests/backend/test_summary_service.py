import pytest
from fastapi.testclient import TestClient

from backend.app.core.fixtures import load_generated_manifest
from backend.app.main import app
from backend.app.services.analysis import analysis_store
from backend.app.services.grammar import grammar_service
from backend.app.services.pronunciation import pronunciation_provider
from backend.app.services.scenarios import get_scenario
from backend.app.services.sessions import session_store
from backend.app.services.summary import summary_service


@pytest.fixture(autouse=True)
def clear_session_store() -> None:
    session_store.clear()
    analysis_store.clear()


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


def test_summary_service_prefers_stored_grammar_results(monkeypatch) -> None:
    scenario = get_scenario("interview")
    assert scenario is not None
    session = session_store.create(scenario)
    session.add_turn(
        speaker="user",
        text="I am working in this field since three years.",
    )
    correction = grammar_service.check(
        scenario_id=scenario.id,
        user_text="I am working in this field since three years.",
        conversation_context=[],
    )
    analysis_store.add_grammar_result(session.id, correction)

    def fail_check(**kwargs):
        del kwargs
        raise AssertionError("summary should use stored grammar analysis")

    monkeypatch.setattr("backend.app.services.summary.grammar_service.check", fail_check)

    summary = summary_service.summarize(session=session, scenario=scenario)

    assert summary.grammar_score == 70
    assert "preposition" in summary.top_issues


def test_summary_service_uses_stored_pronunciation_results() -> None:
    scenario = get_scenario("interview")
    assert scenario is not None
    session = session_store.create(scenario)
    item = load_generated_manifest("speechocean762")["items"][0]
    assessment = pronunciation_provider.assess(fixture_id=item["id"])
    assert assessment is not None
    analysis_store.add_pronunciation_result(session.id, assessment)

    summary = summary_service.summarize(session=session, scenario=scenario)

    assert summary.pronunciation_score == assessment.overall
    assert any("theme" in issue.lower() for issue in summary.top_issues)
    assert any("pronouncing" in drill for drill in summary.next_drills)


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
