from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services.analysis import analysis_store
from backend.app.services.dialogue import DialogueService
from backend.app.services.llm import FakeLLMClient
from backend.app.services.sessions import session_store


def test_audio_websocket_streaming_reply_reports_itl(monkeypatch) -> None:
    session_store.clear()
    analysis_store.clear()
    monkeypatch.setattr(
        "backend.app.main.dialogue_service",
        DialogueService(FakeLLMClient(responses=["Sure, here is a longer reply with several words."])),
    )
    client = TestClient(app)
    created = client.post("/api/sessions", json={"scenario_id": "interview"}).json()
    session_id = created["session"]["id"]

    reply_timing = None
    with client.websocket_connect(f"/ws/sessions/{session_id}/audio") as websocket:
        websocket.send_json(
            {
                "type": "start_turn",
                "expected_text": "My weekend was relaxing and quiet overall.",
            }
        )
        websocket.receive_json()
        websocket.send_bytes(b"fake-audio-chunk")
        websocket.send_json({"type": "end_turn"})
        while True:
            event = websocket.receive_json()
            if event["type"] == "debug.timing" and event["stage"] == "reply":
                reply_timing = event
                break

    assert reply_timing is not None
    timings = reply_timing["timings"]
    assert timings["reply_first_delta_ms"] >= 0
    assert timings["reply_delta_count"] >= 2
    assert timings["reply_total_stream_ms"] >= 0
    assert timings["reply_itl_ms"] >= 0
