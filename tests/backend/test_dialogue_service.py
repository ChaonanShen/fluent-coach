import pytest
from fastapi.testclient import TestClient

from backend.app.core.fixtures import load_text_fixture
from backend.app.main import app
from backend.app.services.dialogue import dialogue_service
from backend.app.services.dialogue import DialogueService
from backend.app.services.llm import FakeLLMClient
from backend.app.services.scenarios import get_scenario
from backend.app.services.scenarios import make_custom_scenario
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
    assert body["grammar_result"]["user_text"].startswith("Sure. I have three years")


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
    assert "Always reply in English" in service.llm_client.calls[0][0].content
    assert "avoid definitive professional conclusions" in service.llm_client.calls[0][0].content


def test_dialogue_service_streams_unmatched_text() -> None:
    scenario = get_scenario("interview")
    assert scenario is not None
    session = session_store.create(scenario)
    service = DialogueService(FakeLLMClient(responses=["That sounds useful. What did you own?"]))

    reply = service.generate_reply_stream(
        session=session,
        scenario=scenario,
        user_text="I built an internal platform at my last company.",
    )

    assert reply is not None
    assert "".join(reply.chunks) == "That sounds useful. What did you own?"
    assert reply.current_goal in scenario.conversation_goals
    assert "Always reply in English" in service.llm_client.calls[0][0].content
    assert "avoid definitive professional conclusions" in service.llm_client.calls[0][0].content


def test_custom_dialogue_fallback_replies_in_english_for_chinese_prompt() -> None:
    scenario = make_custom_scenario("我希望你扮演一位医生，我向你问诊")
    session = session_store.create(scenario, custom_scenario=scenario, custom_prompt="我希望你扮演一位医生，我向你问诊")
    service = DialogueService()

    reply = service.generate_reply(
        session=session,
        scenario=scenario,
        user_text="我头疼，想咨询一下。",
    )

    assert reply.text == "Thanks. Could you tell me a little more?"
    assert not _contains_cjk(reply.text)


def test_dialogue_service_streams_fixture_replies() -> None:
    scenario = get_scenario("interview")
    assert scenario is not None
    session = session_store.create(scenario)
    service = DialogueService(FakeLLMClient(responses=["should not stream"]))

    reply = service.generate_reply_stream(
        session=session,
        scenario=scenario,
        user_text="Sure. I have three years of experience in backend development, mainly building APIs and data services.",
    )

    assert "".join(reply.chunks) == "Great. Which project from that experience is most relevant to this role?"
    assert reply.next_intent == "continue_fixture_dialogue"


def test_dialogue_service_streams_fallback_replies_without_llm() -> None:
    scenario = get_scenario("meeting")
    assert scenario is not None
    session = session_store.create(scenario)
    service = DialogueService()

    reply = service.generate_reply_stream(
        session=session,
        scenario=scenario,
        user_text="The deployment finished yesterday and the metrics look stable.",
    )

    assert "".join(reply.chunks) == "Thanks for the update. What is the main risk we should track next?"
    assert reply.next_intent == "ask_for_specific_example"


def test_stream_prompt_does_not_duplicate_current_user_turn() -> None:
    scenario = get_scenario("interview")
    assert scenario is not None
    session = session_store.create(scenario)
    user_text = "I built an internal platform at my last company."
    service = DialogueService(FakeLLMClient(responses=["That sounds useful. What did you own?"]))
    user_turn = service.create_user_turn(session=session, user_text=user_text)

    reply = service.generate_reply_stream(
        session=session,
        scenario=scenario,
        user_text=user_text,
        exclude_turn_id=user_turn.id,
    )

    assert "".join(reply.chunks) == "That sounds useful. What did you own?"
    prompt = service.llm_client.calls[0][1].content
    assert prompt.count(user_text) == 1


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


def _contains_cjk(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)
