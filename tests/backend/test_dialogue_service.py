import pytest
from fastapi.testclient import TestClient

from backend.app.core.fixtures import load_text_fixture
from backend.app.main import app
from backend.app.services.dialogue import dialogue_service
from backend.app.services.dialogue import DialogueService
from backend.app.services.llm import FakeLLMClient
from backend.app.services.scenarios import get_scenario
from backend.app.services.sessions import session_store


@pytest.fixture(autouse=True)
def clear_session_store() -> None:
    session_store.clear()


def test_dialogue_service_matches_fixture_next_ai_turns() -> None:
    for sample in load_text_fixture("dialogue_samples")["samples"]:
        scenario = get_scenario(sample["scenario_id"])
        assert scenario is not None
        session = session_store.create(scenario)
        turns = sample["turns"]
        for index, turn in enumerate(turns[:-1]):
            if turn["speaker"] != "user":
                continue
            next_turn = turns[index + 1]
            if next_turn["speaker"] != "ai":
                continue

            reply = dialogue_service.generate_reply(
                session=session,
                scenario=scenario,
                user_text=turn["text"],
            )

            assert reply.text == next_turn["text"]
            assert reply.current_goal in scenario.conversation_goals


def test_text_turn_api_appends_user_and_ai_turns() -> None:
    client = TestClient(app)
    created = client.post("/api/sessions", json={"scenario_id": "interview"}).json()
    session_id = created["session"]["id"]

    response = client.post(
        f"/api/sessions/{session_id}/turns/text",
        json={
            "text": "Sure. I have three years of experience in backend development, mainly building APIs and data services."
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["user_turn"]["speaker"] == "user"
    assert body["ai_turn"]["speaker"] == "ai"
    assert body["ai_turn"]["text"] == "Great. Which project from that experience is most relevant to this role?"
    assert len(body["session"]["turns"]) == 3
    assert body["current_goal"]
    assert body["next_intent"] == "continue_fixture_dialogue"


def test_dialogue_service_uses_llm_for_unmatched_text() -> None:
    scenario = get_scenario("interview")
    assert scenario is not None
    session = session_store.create(scenario)
    service = DialogueService(
        FakeLLMClient(
            responses=[
                """
                {
                  "reply_text": "That sounds useful. What was your specific contribution?",
                  "current_goal": "Explain one relevant project or achievement",
                  "next_intent": "ask_for_specific_contribution"
                }
                """
            ]
        )
    )

    reply = service.generate_reply(
        session=session,
        scenario=scenario,
        user_text="I built an internal platform at my last company.",
    )

    assert reply.text == "That sounds useful. What was your specific contribution?"
    assert reply.next_intent == "ask_for_specific_contribution"


def test_text_turn_api_uses_fallback_for_unmatched_text() -> None:
    client = TestClient(app)
    created = client.post("/api/sessions", json={"scenario_id": "meeting"}).json()
    session_id = created["session"]["id"]

    response = client.post(
        f"/api/sessions/{session_id}/turns/text",
        json={"text": "The deployment finished yesterday and the metrics look stable."},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ai_turn"]["text"] == "Thanks for the update. What is the main risk we should track next?"
    assert body["next_intent"] == "ask_for_specific_example"


def test_text_turn_api_rejects_unknown_session() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/sessions/not-found/turns/text",
        json={"text": "Hello"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Unknown session"
