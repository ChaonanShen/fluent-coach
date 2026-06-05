from fastapi.testclient import TestClient

from backend.app.core.fixtures import load_text_fixture
from backend.app.main import app
from backend.app.models import CorrectionTiming
from backend.app.services.grammar import grammar_service


def test_grammar_service_matches_all_handwritten_fixtures() -> None:
    items = load_text_fixture("grammar_expression_errors")["items"]

    for item in items:
        correction = grammar_service.check(
            scenario_id=item["scenario_id"],
            user_text=item["original_text"],
            conversation_context=[],
        )

        assert correction.corrected_text == item["expected_corrected_text"]
        assert correction.better_expression == item["better_expression"]
        assert correction.overall_severity == item["severity"]
        assert correction.correction_timing == item["correction_timing"]
        assert correction.issues
        assert correction.issues[0].original_span in item["original_text"]


def test_grammar_service_preserves_major_error_timing() -> None:
    item = next(
        case
        for case in load_text_fixture("grammar_expression_errors")["items"]
        if case["severity"] == "major" and case["correction_timing"] == "immediate_light"
    )

    correction = grammar_service.check(
        scenario_id=item["scenario_id"],
        user_text=item["original_text"],
        conversation_context=[],
    )

    assert correction.overall_severity == "major"
    assert correction.correction_timing == CorrectionTiming.IMMEDIATE_LIGHT


def test_grammar_service_returns_noop_for_unknown_sentence() -> None:
    correction = grammar_service.check(
        scenario_id="interview",
        user_text="I have worked on backend systems for three years.",
        conversation_context=[],
    )

    assert correction.corrected_text == correction.user_text
    assert correction.issues == []
    assert correction.correction_timing == CorrectionTiming.DELAYED_SUMMARY


def test_grammar_check_api_returns_correction() -> None:
    client = TestClient(app)
    item = load_text_fixture("grammar_expression_errors")["items"][0]

    response = client.post(
        "/api/grammar/check",
        json={
            "scenario_id": item["scenario_id"],
            "user_text": item["original_text"],
            "conversation_context": [],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["corrected_text"] == item["expected_corrected_text"]
    assert body["issues"][0]["original_span"] in item["original_text"]


def test_grammar_check_api_rejects_unknown_scenario() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/grammar/check",
        json={
            "scenario_id": "unknown",
            "user_text": "I am interest this job.",
            "conversation_context": [],
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Unknown scenario"
