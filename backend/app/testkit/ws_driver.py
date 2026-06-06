from __future__ import annotations

import os
from collections.abc import Sequence
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType
from typing import Any

from fastapi.testclient import TestClient

from backend.app.eval.metrics import word_error_rate
from backend.app.models import TurnSpeaker
from backend.app.services.asr import FakeASR
from backend.app.services.llm import FakeLLMClient
from backend.app.testkit.models import TurnRecord
from backend.app.testkit.scripts_data import scripted_user_lines


FAKE_REPLY = "Thanks for sharing that. Could you give one specific example with the result?"


def run_ws_conversation(
    *,
    scenario_id: str,
    turns: int,
    app: Any | None = None,
    transcript_source: str = "scripted",
    mode: str = "offline_fake",
    audio_paths: Sequence[str | Path] | None = None,
) -> list[TurnRecord]:
    if turns < 0:
        raise ValueError("turns must be non-negative")
    main_module = _main_module()
    target_app = app or main_module.app
    expected_lines = _expected_lines(scenario_id, turns, transcript_source, mode)
    audio_files = [Path(path) for path in audio_paths or []]
    if mode != "offline_fake" and not audio_files:
        raise ValueError("real bench mode requires --audio-file or --audio-dir")

    with _offline_provider_patch(main_module, enabled=mode == "offline_fake"):
        client = TestClient(target_app)
        created = client.post("/api/sessions", json={"scenario_id": scenario_id})
        created.raise_for_status()
        session_id = created.json()["session"]["id"]
        records: list[TurnRecord] = []

        with client.websocket_connect(f"/ws/sessions/{session_id}/audio") as websocket:
            for index in range(turns):
                expected_text = expected_lines[index] if index < len(expected_lines) else None
                audio_bytes, mime_type = _audio_payload(
                    index=index,
                    mode=mode,
                    audio_files=audio_files,
                )
                event = {"type": "start_turn", "mime_type": mime_type}
                if expected_text:
                    event["expected_text"] = expected_text
                websocket.send_json(event)
                websocket.receive_json()
                websocket.send_bytes(audio_bytes)
                websocket.send_json({"type": "end_turn"})
                records.append(
                    _collect_turn(
                        websocket=websocket,
                        main_module=main_module,
                        session_id=session_id,
                        index=index,
                        expected_text=expected_text,
                    )
                )

        _merge_analysis_fallback(client, session_id, records)
        return records


def _collect_turn(
    *,
    websocket: Any,
    main_module: ModuleType,
    session_id: str,
    index: int,
    expected_text: str | None,
) -> TurnRecord:
    asr_text = ""
    reply_text = ""
    reply_chunks: list[str] = []
    grammar: dict[str, object] | None = None
    pronunciation: dict[str, object] | None = None
    errors: list[dict[str, object]] = []
    timings_ms: dict[str, float] = {}
    reply_terminal = False
    pending_received = False
    grammar_terminal = False
    pronunciation_expected = False
    pronunciation_terminal = False

    for _ in range(120):
        event = websocket.receive_json()
        event_type = event.get("type")
        if event_type == "asr.final":
            asr_text = str(event.get("text") or "")
        elif event_type == "reply.delta":
            reply_chunks.append(str(event.get("text") or ""))
        elif event_type == "reply.text":
            reply_text = str(event.get("text") or "")
            reply_terminal = True
        elif event_type == "reply.done":
            reply_text = str(event.get("text") or "") or "".join(reply_chunks)
            reply_terminal = True
        elif event_type == "debug.timing":
            timings_ms.update(_float_timings(event.get("timings")))
        elif event_type == "analysis.pending":
            pending_received = True
            stages = event.get("stages") or []
            pronunciation_expected = "pronunciation" in stages
        elif event_type == "analysis.result":
            stage = event.get("stage")
            result = event.get("result")
            if stage == "grammar":
                grammar = result if isinstance(result, dict) else None
                grammar_terminal = True
            elif stage == "pronunciation":
                pronunciation = result if isinstance(result, dict) else None
                pronunciation_terminal = True
        elif event_type == "analysis.error":
            errors.append(_analysis_error_payload(event))
            if event.get("stage") == "grammar":
                grammar_terminal = True
            elif event.get("stage") == "pronunciation":
                pronunciation_terminal = True
        elif event_type == "error":
            raise RuntimeError(f"bench websocket error: {event.get('code') or event}")

        if (
            reply_terminal
            and pending_received
            and grammar_terminal
            and (not pronunciation_expected or pronunciation_terminal)
        ):
            break
    else:
        raise RuntimeError("Timed out waiting for WebSocket turn analysis events")

    if not reply_text:
        reply_text = "".join(reply_chunks).strip()
    user_text = expected_text or asr_text
    audio_path = _latest_audio_path(main_module, session_id)
    wer = word_error_rate(expected_text, asr_text) if expected_text is not None else None
    return TurnRecord(
        index=index,
        user_text=user_text,
        asr_text=asr_text,
        expected_text=expected_text,
        audio_path=audio_path,
        reply_text=reply_text,
        grammar=grammar,
        pronunciation=pronunciation,
        errors=errors,
        timings_ms=timings_ms,
        wer=wer,
    )


def _merge_analysis_fallback(client: TestClient, session_id: str, records: list[TurnRecord]) -> None:
    response = client.get(f"/api/sessions/{session_id}/analysis")
    if response.status_code != 200:
        return
    analysis = response.json()
    grammar_results = analysis.get("grammar_results") or []
    pronunciation_results = analysis.get("pronunciation_results") or []
    errors = analysis.get("errors") or []
    for index, record in enumerate(records):
        if record.grammar is None and index < len(grammar_results):
            record.grammar = grammar_results[index]
        if record.pronunciation is None and index < len(pronunciation_results):
            record.pronunciation = pronunciation_results[index]
        if not record.errors and errors:
            record.errors = [error for error in errors if isinstance(error, dict)]


def _expected_lines(scenario_id: str, turns: int, transcript_source: str, mode: str) -> list[str | None]:
    if mode != "offline_fake":
        return [None] * turns
    if transcript_source != "scripted":
        raise ValueError(f"Unsupported transcript_source: {transcript_source}")
    return scripted_user_lines(scenario_id, turns)


def _audio_payload(
    *,
    index: int,
    mode: str,
    audio_files: Sequence[Path],
) -> tuple[bytes, str]:
    if mode == "offline_fake":
        return b"fake-wav-audio", "audio/wav"
    path = audio_files[index % len(audio_files)]
    return path.read_bytes(), _mime_type(path)


def _mime_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".wav":
        return "audio/wav"
    if suffix == ".mp3":
        return "audio/mpeg"
    if suffix == ".ogg":
        return "audio/ogg"
    if suffix == ".webm":
        return "audio/webm"
    if suffix == ".flac":
        return "audio/flac"
    return "application/octet-stream"


def _float_timings(raw_timings: object) -> dict[str, float]:
    if not isinstance(raw_timings, dict):
        return {}
    timings: dict[str, float] = {}
    for key, value in raw_timings.items():
        if isinstance(value, bool) or not isinstance(value, int | float):
            continue
        timings[str(key)] = float(value)
    return timings


def _analysis_error_payload(event: dict[str, object]) -> dict[str, object]:
    raw_error = event.get("error")
    if isinstance(raw_error, dict):
        payload = dict(raw_error)
    else:
        payload = {}
    if event.get("stage") is not None:
        payload.setdefault("stage", event["stage"])
    if event.get("turn_id") is not None:
        payload.setdefault("turn_id", event["turn_id"])
    return payload


def _latest_audio_path(main_module: ModuleType, session_id: str) -> str | None:
    session = main_module.session_store.get(session_id)
    if session is None:
        return None
    for turn in reversed(session.turns):
        if turn.speaker == TurnSpeaker.USER and turn.audio_path:
            return turn.audio_path
    return None


def _main_module() -> ModuleType:
    from backend.app import main

    return main


@contextmanager
def _offline_provider_patch(main_module: ModuleType, *, enabled: bool):
    if not enabled:
        yield
        return

    previous_asr = main_module.asr_provider
    previous_llm = main_module.dialogue_service.llm_client
    previous_pron_env = os.environ.get("PRON_ASSESS_AUDIO_TURNS")
    main_module.asr_provider = FakeASR()
    main_module.dialogue_service.llm_client = FakeLLMClient(responses=[FAKE_REPLY])
    os.environ["PRON_ASSESS_AUDIO_TURNS"] = "0"
    try:
        yield
    finally:
        main_module.asr_provider = previous_asr
        main_module.dialogue_service.llm_client = previous_llm
        if previous_pron_env is None:
            os.environ.pop("PRON_ASSESS_AUDIO_TURNS", None)
        else:
            os.environ["PRON_ASSESS_AUDIO_TURNS"] = previous_pron_env
