import pytest
import time
from fastapi.testclient import TestClient
from pathlib import Path

from backend.app.models import CorrectionTiming, GrammarCorrection, GrammarSeverity
from backend.app.main import app
from backend.app.services.analysis import analysis_store
from backend.app.services.sessions import session_store


@pytest.fixture(autouse=True)
def clear_session_store() -> None:
    session_store.clear()
    analysis_store.clear()


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


def test_audio_websocket_emits_reply_and_grammar_timings() -> None:
    client = TestClient(app)
    created = client.post("/api/sessions", json={"scenario_id": "interview"}).json()
    session_id = created["session"]["id"]

    with client.websocket_connect(f"/ws/sessions/{session_id}/audio") as websocket:
        websocket.send_json(
            {
                "type": "start_turn",
                "expected_text": "I have worked on backend systems for three years.",
            }
        )
        websocket.receive_json()
        websocket.send_bytes(b"fake-audio-chunk")
        websocket.send_json({"type": "end_turn"})
        websocket.receive_json()
        websocket.receive_json()
        reply_timing = websocket.receive_json()
        pending = websocket.receive_json()
        grammar_timing = websocket.receive_json()

    assert reply_timing["type"] == "debug.timing"
    assert reply_timing["stage"] == "reply"
    assert reply_timing["timings"]["audio_total_ms"] >= 0
    assert reply_timing["timings"]["asr_ms"] >= 0
    assert reply_timing["timings"]["dialogue_reply_ms"] >= 0
    assert reply_timing["timings"]["end_turn_to_asr_final_ms"] >= 0
    assert reply_timing["timings"]["end_turn_to_reply_text_ms"] >= 0
    assert pending["type"] == "analysis.pending"
    assert grammar_timing["type"] == "debug.timing"
    assert grammar_timing["stage"] == "grammar"
    assert grammar_timing["timings"]["grammar_ms"] >= 0


def test_audio_websocket_reply_does_not_wait_for_slow_grammar(monkeypatch) -> None:
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
    created = client.post("/api/sessions", json={"scenario_id": "interview"}).json()
    session_id = created["session"]["id"]

    with client.websocket_connect(f"/ws/sessions/{session_id}/audio") as websocket:
        websocket.send_json(
            {
                "type": "start_turn",
                "expected_text": "I have worked on backend systems for three years.",
            }
        )
        websocket.receive_json()
        websocket.send_bytes(b"fake-audio-chunk")
        started = time.perf_counter()
        websocket.send_json({"type": "end_turn"})
        websocket.receive_json()
        reply = websocket.receive_json()
        websocket.receive_json()
        pending = websocket.receive_json()
        elapsed_before_pending = time.perf_counter() - started
        grammar_timing = websocket.receive_json()
        analysis = websocket.receive_json()

    assert reply["type"] == "reply.text"
    assert pending["type"] == "analysis.pending"
    assert elapsed_before_pending < 0.25
    assert grammar_timing["type"] == "debug.timing"
    assert analysis["type"] == "analysis.result"


def test_audio_websocket_saves_audio_turn_file(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("APP_AUDIO_DIR", str(tmp_path))
    client = TestClient(app)
    created = client.post("/api/sessions", json={"scenario_id": "interview"}).json()
    session_id = created["session"]["id"]

    with client.websocket_connect(f"/ws/sessions/{session_id}/audio") as websocket:
        websocket.send_json(
            {
                "type": "start_turn",
                "expected_text": "I have worked on backend systems for three years.",
                "mime_type": "audio/webm",
            }
        )
        websocket.receive_json()
        websocket.send_bytes(b"fake-webm-audio")
        websocket.send_json({"type": "end_turn"})
        websocket.receive_json()
        reply = websocket.receive_json()

    session = session_store.get(session_id)
    user_turn = next(turn for turn in session.turns if turn.speaker == "user")
    audio_path = Path(user_turn.audio_path)

    assert reply["type"] == "reply.text"
    assert user_turn.mode == "audio"
    assert audio_path.exists()
    assert audio_path.read_bytes() == b"fake-webm-audio"
    assert tmp_path in audio_path.parents


def test_audio_websocket_transcribes_stored_audio_path(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("APP_AUDIO_DIR", str(tmp_path))
    seen_paths: list[Path] = []

    class PathAwareASR:
        provider_name = "path-aware"

        def partial(self, expected_text=None):
            del expected_text
            return ""

        def transcribe(self, audio_bytes, expected_text=None):
            del audio_bytes, expected_text
            raise AssertionError("websocket should transcribe the stored audio file path")

        def transcribe_file(self, audio_path, expected_text=None):
            seen_paths.append(Path(audio_path))
            return expected_text or "I have worked on backend systems for three years."

    monkeypatch.setattr("backend.app.main.asr_provider", PathAwareASR())
    client = TestClient(app)
    created = client.post("/api/sessions", json={"scenario_id": "interview"}).json()
    session_id = created["session"]["id"]

    with client.websocket_connect(f"/ws/sessions/{session_id}/audio") as websocket:
        websocket.send_json(
            {
                "type": "start_turn",
                "expected_text": "I have worked on backend systems for three years.",
                "mime_type": "audio/wav",
            }
        )
        websocket.receive_json()
        websocket.send_bytes(b"fake-wav-audio")
        websocket.send_json({"type": "end_turn"})
        final = websocket.receive_json()

    assert final["type"] == "asr.final"
    assert seen_paths
    assert seen_paths[0].suffix == ".wav"
    assert seen_paths[0].read_bytes() == b"fake-wav-audio"
    assert tmp_path in seen_paths[0].parents


def test_audio_websocket_reports_asr_provider_error(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("APP_AUDIO_DIR", str(tmp_path))

    class BrokenASR:
        provider_name = "faster_whisper"

        def partial(self, expected_text=None):
            del expected_text
            return ""

        def transcribe(self, audio_bytes, expected_text=None):
            del audio_bytes, expected_text
            raise AssertionError("websocket should transcribe stored files")

        def transcribe_file(self, audio_path, expected_text=None):
            del audio_path, expected_text
            raise RuntimeError("faster-whisper is not installed")

    monkeypatch.setattr("backend.app.main.asr_provider", BrokenASR())
    client = TestClient(app)
    created = client.post("/api/sessions", json={"scenario_id": "interview"}).json()
    session_id = created["session"]["id"]

    with client.websocket_connect(f"/ws/sessions/{session_id}/audio") as websocket:
        websocket.send_json({"type": "start_turn", "mime_type": "audio/wav"})
        websocket.receive_json()
        websocket.send_bytes(b"fake-wav-audio")
        websocket.send_json({"type": "end_turn"})
        timing = websocket.receive_json()
        event = websocket.receive_json()

    assert timing["type"] == "debug.timing"
    assert timing["stage"] == "asr"
    assert event["type"] == "analysis.error"
    assert event["stage"] == "asr"
    assert event["error"]["code"] == "provider_dependency_missing"
    assert event["error"]["stage"] == "asr"

    analysis = client.get(f"/api/sessions/{session_id}/analysis").json()
    assert analysis["errors"][0]["code"] == "provider_dependency_missing"


def test_audio_websocket_reports_missing_ffmpeg_for_real_asr(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("APP_AUDIO_DIR", str(tmp_path))
    monkeypatch.setattr("backend.app.services.audio.shutil.which", lambda name: None)

    class RealASR:
        provider_name = "faster_whisper"

        def partial(self, expected_text=None):
            del expected_text
            return ""

        def transcribe(self, audio_bytes, expected_text=None):
            del audio_bytes, expected_text
            raise AssertionError("websocket should not call byte ASR")

        def transcribe_file(self, audio_path, expected_text=None):
            del audio_path, expected_text
            raise AssertionError("websocket should stop before ASR when ffmpeg is missing")

    monkeypatch.setattr("backend.app.main.asr_provider", RealASR())
    client = TestClient(app)
    created = client.post("/api/sessions", json={"scenario_id": "interview"}).json()
    session_id = created["session"]["id"]

    with client.websocket_connect(f"/ws/sessions/{session_id}/audio") as websocket:
        websocket.send_json({"type": "start_turn", "mime_type": "audio/webm"})
        websocket.receive_json()
        websocket.send_bytes(b"fake-webm-audio")
        websocket.send_json({"type": "end_turn"})
        timing = websocket.receive_json()
        event = websocket.receive_json()

    assert timing["type"] == "debug.timing"
    assert timing["stage"] == "asr"
    assert event["type"] == "analysis.error"
    assert event["stage"] == "asr"
    assert event["error"]["code"] == "provider_dependency_missing"
    assert "ffmpeg" in event["error"]["user_message_zh"]


def test_audio_websocket_reports_empty_asr_transcript(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("APP_AUDIO_DIR", str(tmp_path))

    class EmptyASR:
        provider_name = "faster_whisper"

        def partial(self, expected_text=None):
            del expected_text
            return ""

        def transcribe(self, audio_bytes, expected_text=None):
            del audio_bytes, expected_text
            raise AssertionError("websocket should transcribe stored files")

        def transcribe_file(self, audio_path, expected_text=None):
            del audio_path, expected_text
            return "   "

    monkeypatch.setattr("backend.app.main.asr_provider", EmptyASR())
    client = TestClient(app)
    created = client.post("/api/sessions", json={"scenario_id": "interview"}).json()
    session_id = created["session"]["id"]

    with client.websocket_connect(f"/ws/sessions/{session_id}/audio") as websocket:
        websocket.send_json({"type": "start_turn", "mime_type": "audio/wav"})
        websocket.receive_json()
        websocket.send_bytes(b"fake-wav-audio")
        websocket.send_json({"type": "end_turn"})
        timing = websocket.receive_json()
        event = websocket.receive_json()

    assert timing["type"] == "debug.timing"
    assert timing["stage"] == "asr"
    assert event["type"] == "analysis.error"
    assert event["stage"] == "asr"
    assert event["error"]["code"] == "asr_no_speech"


def test_audio_websocket_rejects_empty_audio_turn() -> None:
    client = TestClient(app)
    created = client.post("/api/sessions", json={"scenario_id": "interview"}).json()
    session_id = created["session"]["id"]

    with client.websocket_connect(f"/ws/sessions/{session_id}/audio") as websocket:
        websocket.send_json({"type": "start_turn"})
        websocket.receive_json()
        websocket.send_json({"type": "end_turn"})
        event = websocket.receive_json()

    assert event["type"] == "error"
    assert event["code"] == "empty_audio"


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
