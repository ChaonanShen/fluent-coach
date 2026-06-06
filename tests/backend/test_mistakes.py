import pytest
from fastapi.testclient import TestClient

from backend.app.core.fixtures import load_generated_manifest, load_text_fixture
from backend.app.main import app
from backend.app.models import PronunciationAssessment, PronunciationIssue
from backend.app.services.llm import FakeLLMClient
from backend.app.services.mistakes import MistakeService, _pronunciation_practice_sentence
from backend.app.services.sessions import session_store
from backend.app.services.storage import log_store


@pytest.fixture(autouse=True)
def clear_log_store() -> None:
    log_store.clear_all()
    session_store.clear()


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


def test_text_turn_mistakes_keep_session_and_turn_source() -> None:
    client = TestClient(app)
    created = client.post("/api/sessions", json={"scenario_id": "interview"}).json()
    session_id = created["session"]["id"]

    turn_response = client.post(
        f"/api/sessions/{session_id}/turns/text",
        json={"text": "I am working in this field since three years."},
    )
    mistakes = client.get("/api/mistakes", params={"session_id": session_id}).json()["mistakes"]
    other_session_mistakes = client.get("/api/mistakes", params={"session_id": "not-this-session"}).json()["mistakes"]

    assert turn_response.status_code == 200
    user_turn_id = turn_response.json()["user_turn"]["id"]
    assert mistakes
    assert {mistake["session_id"] for mistake in mistakes} == {session_id}
    assert {mistake["turn_id"] for mistake in mistakes} == {user_turn_id}
    assert {mistake["source_stage"] for mistake in mistakes} >= {"grammar"}
    assert all(mistake["source_id"] for mistake in mistakes)
    assert all(mistake["subtype"] for mistake in mistakes)
    assert other_session_mistakes == []


def test_pronunciation_assessment_generates_pronunciation_mistakes() -> None:
    client = TestClient(app)
    item = load_generated_manifest("speechocean762")["items"][0]

    response = client.post("/api/pronunciation/assess", json={"fixture_id": item["id"]})
    mistakes = client.get("/api/mistakes").json()["mistakes"]

    assert response.status_code == 200
    pronunciation = [mistake for mistake in mistakes if mistake["type"] == "pronunciation"]
    assert pronunciation
    assert {mistake["word"].lower() for mistake in pronunciation} >= {"theme"}
    theme = next(mistake for mistake in pronunciation if mistake["word"].lower() == "theme")
    assert theme["practice_sentence"] != response.json()["reference_text"]
    assert theme["practice_sentence"] == "The theme of the presentation was clear and focused."
    assert not theme["practice_sentence"].lower().startswith("please say")
    assert "theme" in theme["practice_sentence"].lower()


def test_pronunciation_practice_sentence_uses_real_examples() -> None:
    systems_sentence = _pronunciation_practice_sentence("systems")
    working_sentence = _pronunciation_practice_sentence("working")
    three_sentence = _pronunciation_practice_sentence("three")

    assert systems_sentence == "The team reviewed the systems before launch."
    assert "please say" not in systems_sentence.lower()
    assert working_sentence == "I am working with the team this afternoon."
    assert "working" in working_sentence
    assert three_sentence == "I have three ideas for tomorrow's meeting."
    assert "short answer" not in three_sentence.lower()


def test_pronunciation_practice_sentence_uses_llm_when_available() -> None:
    llm = FakeLLMClient(
        responses=[
            """
            {
              "three": "I have three meetings before lunch.",
              "systems": "Our systems handled the traffic well."
            }
            """
        ]
    )
    service = MistakeService(log_store, llm_client=llm)
    assessment = PronunciationAssessment(
        provider="mock",
        reference_text="I have three systems.",
        overall=52,
        accuracy=48,
        fluency=70,
        issues=[
            PronunciationIssue(
                kind="word_accuracy",
                target="three",
                message_zh="`three` 发音准确度偏低，建议单独跟读。",
            ),
            PronunciationIssue(
                kind="word_accuracy",
                target="systems",
                message_zh="`systems` 发音准确度偏低，建议单独跟读。",
            )
        ],
    )

    mistakes = service.add_from_pronunciation(assessment, session_id="session_1", turn_id="turn_1")

    assert len(llm.calls) == 1
    assert "three" in llm.calls[0][1].content
    assert "systems" in llm.calls[0][1].content
    assert [mistake.practice_sentence for mistake in mistakes] == [
        "I have three meetings before lunch.",
        "Our systems handled the traffic well.",
    ]


def test_pronunciation_practice_sentence_rejects_prompt_like_llm_output() -> None:
    llm = FakeLLMClient(responses=["Please say three clearly in this short sentence."])

    sentence = _pronunciation_practice_sentence("three", llm)

    assert sentence == "I have three ideas for tomorrow's meeting."
    assert "please say" not in sentence.lower()


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


def test_delete_mistake_removes_item_and_updates_book_counts() -> None:
    client = TestClient(app)
    created = client.post("/api/sessions", json={"scenario_id": "interview"}).json()
    session_id = created["session"]["id"]
    client.post(
        f"/api/sessions/{session_id}/turns/text",
        json={"text": "I am working in this field since three years."},
    )
    mistakes = client.get("/api/mistakes", params={"session_id": session_id}).json()["mistakes"]

    response = client.delete(f"/api/mistakes/{mistakes[0]['id']}")
    remaining_book = client.get(f"/api/mistake-books/{session_id}").json()

    assert response.status_code == 200
    assert response.json()["deleted_count"] == 1
    assert remaining_book["record"]["mistake_count"] == len(mistakes) - 1
    assert mistakes[0]["id"] not in {
        mistake["id"]
        for group in remaining_book["turn_groups"]
        for mistake in group["mistakes"]
    }


def test_delete_mistake_rejects_unknown_id() -> None:
    client = TestClient(app)

    response = client.delete("/api/mistakes/not-found")

    assert response.status_code == 404
    assert response.json()["detail"] == "Unknown mistake"
