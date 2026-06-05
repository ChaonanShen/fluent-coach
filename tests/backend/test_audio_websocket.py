import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services.sessions import session_store


@pytest.fixture(autouse=True)
def clear_session_store() -> None:
    session_store.clear()


def test_audio_websocket_returns_asr_and_reply_events() -> None:
    client = TestClient(app)
    created = client.post("/api/sessions", json={"scenario_id": "interview"}).json()
    session_id = created["session"]["id"]

    with client.websocket_connect(f"/ws/sessions/{session_id}/audio") as websocket:
        websocket.send_json(
            {
                "type": "start_turn",
                "expected_text": "Sure. I have three years of experience in backend development, mainly building APIs and data services.",
            }
        )
        partial = websocket.receive_json()
        websocket.send_bytes(b"fake-audio-chunk")
        websocket.send_json({"type": "end_turn"})
        final = websocket.receive_json()
        reply = websocket.receive_json()

    assert partial["type"] == "asr.partial"
    assert partial["text"] == "Sure. I have three"
    assert final["type"] == "asr.final"
    assert final["text"].startswith("Sure. I have three years")
    assert reply["type"] == "reply.text"
    assert reply["text"] == "Great. Which project from that experience is most relevant to this role?"
    assert reply["next_intent"] == "continue_fixture_dialogue"


def test_audio_websocket_rejects_unknown_session() -> None:
    client = TestClient(app)

    with client.websocket_connect("/ws/sessions/not-found/audio") as websocket:
        event = websocket.receive_json()

    assert event["type"] == "error"
    assert event["code"] == "unknown_session"


def test_audio_websocket_reports_unknown_event() -> None:
    client = TestClient(app)
    created = client.post("/api/sessions", json={"scenario_id": "meeting"}).json()
    session_id = created["session"]["id"]

    with client.websocket_connect(f"/ws/sessions/{session_id}/audio") as websocket:
        websocket.send_json({"type": "bad_event"})
        event = websocket.receive_json()

    assert event["type"] == "error"
    assert event["code"] == "unknown_event"
