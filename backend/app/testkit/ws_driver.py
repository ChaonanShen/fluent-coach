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
from backend.app.testkit.grammar_cases import GrammarErrorCase
from backend.app.testkit.grammar_injection import inject_errors, score_grammar_result
from backend.app.testkit.models import TurnRecord
from backend.app.testkit.scripts_data import scripted_user_lines
from backend.app.testkit.tts_audio import SynthesizingTTSProvider, synthesize_turn_audio
from backend.app.testkit.virtual_user import LLMVirtualUser, TemplateVirtualUser, VirtualUser


FAKE_REPLY = "Thanks for sharing that. Could you give one specific example with the result?"


def run_ws_conversation(
    *,
    scenario_id: str,
    turns: int,
    app: Any | None = None,
    transcript_source: str = "scripted",
    mode: str = "offline_fake",
    audio_paths: Sequence[str | Path] | None = None,
    tts_provider: SynthesizingTTSProvider | None = None,
    virtual_user: VirtualUser | None = None,
    virtual_user_source: str = "template",
    allow_fake_providers: bool = False,
) -> list[TurnRecord]:
    if turns < 0:
        raise ValueError("turns must be non-negative")
    main_module = _main_module()
    target_app = app or main_module.app
    expected_lines = _expected_lines(scenario_id, turns, transcript_source, mode)
    audio_files = [Path(path) for path in audio_paths or []]
    if mode not in {"offline_fake", "grammar_tts"} and not audio_files:
        raise ValueError("real bench mode requires --audio-file or --audio-dir")
    if mode == "grammar_tts":
        _validate_grammar_tts_providers(
            main_module=main_module,
            tts_provider=tts_provider or main_module.tts_provider,
            allow_fake_providers=allow_fake_providers,
        )
    selected_virtual_user = virtual_user or _virtual_user(main_module, virtual_user_source)

    with _offline_provider_patch(main_module, enabled=mode == "offline_fake"):
        client = TestClient(target_app)
        created = client.post("/api/sessions", json={"scenario_id": scenario_id})
        created.raise_for_status()
        session_id = created.json()["session"]["id"]
        records: list[TurnRecord] = []

        with client.websocket_connect(f"/ws/sessions/{session_id}/audio") as websocket:
            for index in range(turns):
                history = _session_history(main_module, session_id)
                turn_context = _prepare_turn_context(
                    index=index,
                    scenario_id=scenario_id,
                    mode=mode,
                    expected_lines=expected_lines,
                    audio_files=audio_files,
                    tts_provider=tts_provider or main_module.tts_provider,
                    virtual_user=selected_virtual_user,
                    history=history,
                )
                event = {"type": "start_turn", "mime_type": turn_context["mime_type"]}
                if turn_context["expected_text"]:
                    event["expected_text"] = turn_context["expected_text"]
                websocket.send_json(event)
                websocket.receive_json()
                websocket.send_bytes(turn_context["audio_bytes"])
                websocket.send_json({"type": "end_turn"})
                records.append(
                    _collect_turn(
                        websocket=websocket,
                        main_module=main_module,
                        session_id=session_id,
                        index=index,
                        expected_text=turn_context["expected_text"],
                        interviewer_text=_last_speaker_text(history, TurnSpeaker.AI.value),
                        clean_text=turn_context.get("clean_text"),
                        injected_text=turn_context.get("injected_text"),
                        expected_corrected_text=turn_context.get("expected_corrected_text"),
                        expected_error_types=turn_context.get("expected_error_types") or [],
                        grammar_case=turn_context.get("grammar_case"),
                        tts_meta=turn_context.get("tts") or {},
                        extra_timings=turn_context.get("timings_ms") or {},
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
    interviewer_text: object = None,
    clean_text: object = None,
    injected_text: object = None,
    expected_corrected_text: object = None,
    expected_error_types: object = None,
    grammar_case: object = None,
    tts_meta: object = None,
    extra_timings: object = None,
) -> TurnRecord:
    asr_text = ""
    reply_text = ""
    reply_chunks: list[str] = []
    grammar: dict[str, object] | None = None
    pronunciation: dict[str, object] | None = None
    errors: list[dict[str, object]] = []
    timings_ms: dict[str, float] = _float_timings(extra_timings)
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
    error_types = [str(value) for value in expected_error_types] if isinstance(expected_error_types, list) else []
    grammar_metrics: dict[str, object] = {}
    if isinstance(grammar_case, GrammarErrorCase):
        grammar_metrics = score_grammar_result(grammar_case, grammar, asr_text)
    return TurnRecord(
        index=index,
        user_text=user_text,
        asr_text=asr_text,
        expected_text=expected_text,
        audio_path=audio_path,
        interviewer_text=str(interviewer_text) if interviewer_text else None,
        reply_text=reply_text,
        grammar=grammar,
        pronunciation=pronunciation,
        errors=errors,
        timings_ms=timings_ms,
        wer=wer,
        clean_text=str(clean_text) if clean_text else None,
        injected_text=str(injected_text) if injected_text else None,
        expected_corrected_text=str(expected_corrected_text) if expected_corrected_text else None,
        expected_error_types=error_types,
        grammar_metrics=grammar_metrics,
        tts=dict(tts_meta) if isinstance(tts_meta, dict) else {},
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


def _prepare_turn_context(
    *,
    index: int,
    scenario_id: str,
    mode: str,
    expected_lines: Sequence[str | None],
    audio_files: Sequence[Path],
    tts_provider: SynthesizingTTSProvider,
    virtual_user: VirtualUser,
    history: list[dict[str, str]],
) -> dict[str, object]:
    if mode == "grammar_tts":
        clean_text = virtual_user.next_clean_turn(
            scenario_id=scenario_id,
            history=history,
            index=index,
        )
        case = inject_errors(clean_text, scenario_id=scenario_id, index=index)
        audio_bytes, mime_type, tts_meta, timings = synthesize_turn_audio(case.injected_text, tts_provider)
        return {
            "audio_bytes": audio_bytes,
            "mime_type": mime_type,
            "expected_text": case.injected_text,
            "clean_text": case.clean_text,
            "injected_text": case.injected_text,
            "expected_corrected_text": case.expected_corrected_text,
            "expected_error_types": list(case.expected_error_types),
            "grammar_case": case,
            "tts": tts_meta,
            "timings_ms": timings,
        }

    expected_text = expected_lines[index] if index < len(expected_lines) else None
    audio_bytes, mime_type = _audio_payload(index=index, mode=mode, audio_files=audio_files)
    return {
        "audio_bytes": audio_bytes,
        "mime_type": mime_type,
        "expected_text": expected_text,
    }


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


def _session_scenario_id(main_module: ModuleType, session_id: str) -> str | None:
    session = main_module.session_store.get(session_id)
    return session.scenario_id if session is not None else None


def _session_history(main_module: ModuleType, session_id: str) -> list[dict[str, str]]:
    session = main_module.session_store.get(session_id)
    if session is None:
        return []
    return [{"speaker": turn.speaker.value, "text": turn.text} for turn in session.turns[-8:]]


def _last_speaker_text(history: list[dict[str, str]], speaker: str) -> str | None:
    for item in reversed(history):
        if item.get("speaker") == speaker and item.get("text"):
            return item["text"]
    return None


def _virtual_user(main_module: ModuleType, source: str) -> VirtualUser:
    if source == "template":
        return TemplateVirtualUser()
    if source == "llm":
        llm_client = main_module.dialogue_service.llm_client
        if llm_client is None:
            return TemplateVirtualUser()
        return LLMVirtualUser(llm_client)
    raise ValueError(f"Unsupported virtual_user_source: {source}")


def _validate_grammar_tts_providers(
    *,
    main_module: ModuleType,
    tts_provider: SynthesizingTTSProvider,
    allow_fake_providers: bool,
) -> None:
    if allow_fake_providers:
        return
    if getattr(main_module.asr_provider, "provider_name", None) == "fake":
        raise ValueError("grammar_tts requires a real ASR provider unless allow_fake_providers=True")
    llm_client = main_module.dialogue_service.llm_client
    if llm_client is None or isinstance(llm_client, FakeLLMClient):
        raise ValueError("grammar_tts requires a real LLM provider unless allow_fake_providers=True")
    if getattr(tts_provider, "provider_name", None) in {"browser", "cloud_disabled", None}:
        raise ValueError("grammar_tts requires an audio-producing TTS provider")


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
