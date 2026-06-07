import time

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from backend.app.main import app
from backend.app.models import CorrectionTiming, GrammarCorrection, GrammarSeverity
from backend.app.services.analysis import analysis_store
from backend.app.services.sessions import session_store


@pytest.fixture(autouse=True)
def clear_state() -> None:
    session_store.clear()
    analysis_store.clear()


def _create_session(client: TestClient, scenario_id: str = "interview") -> str:
    created = client.post("/api/sessions", json={"scenario_id": scenario_id})
    created.raise_for_status()
    return created.json()["session"]["id"]


def _collect_until_grammar_terminal(websocket) -> list[dict]:
    events: list[dict] = []
    for _ in range(100):
        event = websocket.receive_json()
        events.append(event)
        if event["type"] in {"analysis.result", "analysis.error"} and event.get("stage") == "grammar":
            return events
    raise AssertionError("Timed out waiting for grammar terminal event")


def test_text_websocket_sends_user_final_before_reply() -> None:
    client = TestClient(app)
    session_id = _create_session(client)

    with client.websocket_connect(f"/ws/sessions/{session_id}/conversation") as websocket:
        websocket.send_json(
            {
                "type": "text_turn",
                "text": "Sure. I have three years of experience in backend development, mainly building APIs and data services.",
            }
        )
        event = websocket.receive_json()

    session = session_store.get(session_id)
    assert event["type"] == "user.final"
    assert event["turn_id"]
    assert event["text"].startswith("Sure. I have three years")
    assert session is not None
    assert any(turn.id == event["turn_id"] and turn.speaker == "user" for turn in session.turns)


def test_text_websocket_streams_fixture_reply_and_analysis_result() -> None:
    client = TestClient(app)
    session_id = _create_session(client)

    with client.websocket_connect(f"/ws/sessions/{session_id}/conversation") as websocket:
        websocket.send_json(
            {
                "type": "text_turn",
                "text": "Sure. I have three years of experience in backend development, mainly building APIs and data services.",
            }
        )
        events = _collect_until_grammar_terminal(websocket)
        with pytest.raises(WebSocketDisconnect):
            websocket.receive_json()

    user_final = events[0]
    deltas = [event["text"] for event in events if event["type"] == "reply.delta"]
    done = next(event for event in events if event["type"] == "reply.done")
    pending = next(event for event in events if event["type"] == "analysis.pending")
    result = next(event for event in events if event["type"] == "analysis.result")

    assert user_final["type"] == "user.final"
    assert deltas
    assert "".join(deltas) == done["text"]
    assert done["text"] == "Great. Which project from that experience is most relevant to this role?"
    assert done["user_turn_id"] == user_final["turn_id"]
    assert pending["stages"] == ["grammar"]
    assert result["turn_id"] == user_final["turn_id"]
    assert result["result"]["user_text"].startswith("Sure. I have three years")


def test_text_websocket_streams_fallback_reply() -> None:
    client = TestClient(app)
    session_id = _create_session(client, scenario_id="meeting")

    with client.websocket_connect(f"/ws/sessions/{session_id}/conversation") as websocket:
        websocket.send_json(
            {
                "type": "text_turn",
                "text": "The deployment finished yesterday and the metrics look stable.",
            }
        )
        events = _collect_until_grammar_terminal(websocket)

    deltas = [event["text"] for event in events if event["type"] == "reply.delta"]
    done = next(event for event in events if event["type"] == "reply.done")
    assert deltas
    assert done["text"] == "Thanks for the update. What is the main risk we should track next?"


def test_text_websocket_reply_does_not_wait_for_slow_grammar(monkeypatch) -> None:
    class SlowGrammar:
        def check(self, **kwargs):
            time.sleep(0.35)
            return GrammarCorrection(
                scenario_id=kwargs["scenario_id"],
                user_text=kwargs["user_text"],
                corrected_text=kwargs["user_text"],
                issues=[],
                overall_severity=GrammarSeverity.MINOR,
                correction_timing=CorrectionTiming.DELAYED_SUMMARY,
            )

    monkeypatch.setattr("backend.app.main.grammar_service", SlowGrammar())
    client = TestClient(app)
    session_id = _create_session(client)

    with client.websocket_connect(f"/ws/sessions/{session_id}/conversation") as websocket:
        websocket.send_json({"type": "text_turn", "text": "I have worked on backend systems for three years."})
        started = time.perf_counter()
        events: list[dict] = []
        while True:
            event = websocket.receive_json()
            events.append(event)
            if event["type"] == "analysis.pending":
                break
        elapsed_before_pending = time.perf_counter() - started

    assert any(event["type"] == "reply.delta" for event in events)
    assert any(event["type"] == "reply.done" for event in events)
    assert elapsed_before_pending < 0.25


def test_text_websocket_analysis_timeout_sends_error(monkeypatch) -> None:
    class SlowGrammar:
        def check(self, **kwargs):
            time.sleep(0.2)
            return GrammarCorrection(
                scenario_id=kwargs["scenario_id"],
                user_text=kwargs["user_text"],
                corrected_text=kwargs["user_text"],
                issues=[],
                overall_severity=GrammarSeverity.MINOR,
                correction_timing=CorrectionTiming.DELAYED_SUMMARY,
            )

    monkeypatch.setattr("backend.app.main.TEXT_ANALYSIS_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr("backend.app.main.grammar_service", SlowGrammar())
    client = TestClient(app)
    session_id = _create_session(client)

    with client.websocket_connect(f"/ws/sessions/{session_id}/conversation") as websocket:
        websocket.send_json({"type": "text_turn", "text": "I have worked on backend systems for three years."})
        events = _collect_until_grammar_terminal(websocket)

    error = next(event for event in events if event["type"] == "analysis.error")
    assert error["stage"] == "grammar"
    assert error["error"]["code"] == "analysis_timeout"
    assert error["error"]["fallback_applied"] is True
    analysis = client.get(f"/api/sessions/{session_id}/analysis").json()
    assert analysis["errors"][0]["code"] == "analysis_timeout"


def test_text_websocket_rejects_unknown_session() -> None:
    client = TestClient(app)

    with client.websocket_connect("/ws/sessions/not-found/conversation") as websocket:
        event = websocket.receive_json()

    assert event["type"] == "error"
    assert event["code"] == "unknown_session"
