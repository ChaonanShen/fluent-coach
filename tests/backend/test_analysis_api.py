import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services.analysis import analysis_store
from backend.app.services.sessions import session_store


@pytest.fixture(autouse=True)
def clear_state() -> None:
    session_store.clear()
    analysis_store.clear()


def test_text_turn_records_analysis_result_for_session() -> None:
    client = TestClient(app)
    created = client.post("/api/sessions", json={"scenario_id": "interview"}).json()
    session_id = created["session"]["id"]
    client.post(
        f"/api/sessions/{session_id}/turns/text",
        json={"text": "I am working in this field since three years."},
    )

    response = client.get(f"/api/sessions/{session_id}/analysis")

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == session_id
    assert body["grammar_results"]
    assert body["grammar_results"][0]["corrected_text"] == "I have been working in this field for three years."
    assert body["errors"] == []


def test_analysis_api_rejects_unknown_session() -> None:
    client = TestClient(app)

    response = client.get("/api/sessions/not-found/analysis")

    assert response.status_code == 404
    assert response.json()["detail"] == "Unknown session"


def test_audio_websocket_sends_analysis_result_event() -> None:
    client = TestClient(app)
    created = client.post("/api/sessions", json={"scenario_id": "interview"}).json()
    session_id = created["session"]["id"]

    with client.websocket_connect(f"/ws/sessions/{session_id}/audio") as websocket:
        websocket.send_json(
            {
                "type": "start_turn",
                "expected_text": "I am working in this field since three years.",
            }
        )
        websocket.receive_json()
        websocket.send_bytes(b"audio")
        websocket.send_json({"type": "end_turn"})
        websocket.receive_json()
        websocket.receive_json()
        pending = websocket.receive_json()
        result = websocket.receive_json()

    assert pending["type"] == "analysis.pending"
    assert result["type"] == "analysis.result"
    assert result["stage"] == "grammar"
    assert result["result"]["corrected_text"] == "I have been working in this field for three years."


def test_audio_websocket_sends_analysis_error_event() -> None:
    client = TestClient(app)
    created = client.post("/api/sessions", json={"scenario_id": "meeting"}).json()
    session_id = created["session"]["id"]

    with client.websocket_connect(f"/ws/sessions/{session_id}/audio") as websocket:
        websocket.send_json(
            {
                "type": "start_turn",
                "expected_text": "The deployment is ready.",
                "force_analysis_error": True,
            }
        )
        websocket.receive_json()
        websocket.send_bytes(b"audio")
        websocket.send_json({"type": "end_turn"})
        websocket.receive_json()
        websocket.receive_json()
        pending = websocket.receive_json()
        error = websocket.receive_json()

    assert pending["type"] == "analysis.pending"
    assert error["type"] == "analysis.error"
    assert error["error"]["code"] == "forced_analysis_error"
    analysis = client.get(f"/api/sessions/{session_id}/analysis").json()
    assert analysis["errors"][0]["code"] == "forced_analysis_error"
