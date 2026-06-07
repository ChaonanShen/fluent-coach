from __future__ import annotations

import os
import re
import time
from datetime import datetime, timezone
from typing import Any

from backend.app.core.env import provider_status
from backend.app.core.fixtures import load_generated_manifest, load_text_fixture, resolve_fixture_audio
from backend.app.eval.metrics import word_error_rate
from backend.app.services.asr import FakeASR
from backend.app.services.grammar import grammar_service
from backend.app.services.llm import LLMMessage, create_llm_client_from_env
from backend.app.services.pronunciation import MockPronunciationProvider


def run_fixture_smoke_report() -> dict[str, Any]:
    asr = _smoke_asr()
    asr_l2_arctic = _smoke_l2_arctic_fixture_asr()
    grammar = _smoke_grammar()
    pronunciation = _smoke_pronunciation()
    dialogue = _smoke_dialogue_fixture()
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "fixture_fake",
        "external_services_used": False,
        "checks": {
            "asr": asr,
            "asr_l2_arctic": asr_l2_arctic,
            "grammar": grammar,
            "pronunciation": pronunciation,
            "dialogue_fixture": dialogue,
            "ui_manual": {
                "status": "not_run",
                "checklist": [
                    "Start a session from the browser UI.",
                    "Record one voice turn and confirm asr.final plus reply.delta/reply.done appear.",
                    "Record Read Aloud and confirm pronunciation score appears.",
                    "End the session and confirm summary renders.",
                ],
            },
        },
        "latency_ms": {
            "end_turn_to_asr_final": None,
            "asr_final_to_reply_done": None,
            "reply_done_to_tts_start": None,
            "pronunciation_upload_to_result": None,
        },
    }


def run_real_smoke_report() -> dict[str, Any]:
    status = provider_status()
    llm = _smoke_real_llm(status)
    asr = _smoke_real_asr(status)
    asr_l2_arctic = _smoke_real_l2_arctic_asr(status)
    pronunciation = _smoke_real_pronunciation(status)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "real_provider_smoke",
        "external_services_used": bool(status["external_services_enabled"]),
        "provider_status": status,
        "checks": {
            "llm": llm,
            "asr": asr,
            "asr_l2_arctic": asr_l2_arctic,
            "pronunciation": pronunciation,
            "ui_manual": {
                "status": "not_run",
                "checklist": [
                    "Open the browser UI and start a scenario session.",
                    "Record one voice turn and confirm asr.final plus reply.delta/reply.done appear.",
                    "Record Read Aloud and confirm a provider-backed pronunciation result appears.",
                    "End the session and confirm summary includes stored grammar/pronunciation results.",
                ],
            },
        },
        "latency_ms": {
            "end_turn_to_asr_final": asr.get("latency_ms"),
            "asr_final_to_reply_done": llm.get("latency_ms"),
            "reply_done_to_tts_start": None,
            "pronunciation_upload_to_result": pronunciation.get("latency_ms"),
        },
    }


def render_smoke_markdown(report: dict[str, Any]) -> str:
    checks = report["checks"]
    latency = report["latency_ms"]
    provider_lines = _provider_markdown_lines(report.get("provider_status"))
    lines = [
        "# Smoke Report",
        "",
        f"Generated at: `{report['generated_at']}`",
        f"Mode: `{report['mode']}`",
        f"External services used: `{str(report['external_services_used']).lower()}`",
        "",
        *provider_lines,
        "## Checks",
        "",
        *(_check_line("LLM", checks.get("llm"))),
        f"- ASR: {checks['asr']['status']} ({checks['asr']['provider']})",
        *(_check_line("ASR L2-ARCTIC", checks.get("asr_l2_arctic"))),
        *(_check_line("Grammar", checks.get("grammar"))),
        f"- Pronunciation: {checks['pronunciation']['status']} ({checks['pronunciation']['provider']})",
        *(_check_line("Dialogue fixture", checks.get("dialogue_fixture"))),
        f"- UI manual: {checks['ui_manual']['status']}",
        "",
        "## Latency",
        "",
        f"- end_turn -> asr.final: {_format_latency(latency['end_turn_to_asr_final'])}",
        f"- asr.final -> reply.done: {_format_latency(latency['asr_final_to_reply_done'])}",
        f"- reply.done -> tts_start: {_format_latency(latency['reply_done_to_tts_start'])}",
        f"- pronunciation upload -> result: {_format_latency(latency['pronunciation_upload_to_result'])}",
        "",
        "## Manual UI Checklist",
        "",
    ]
    lines.extend(f"- {item}" for item in checks["ui_manual"]["checklist"])
    lines.append("")
    lines.append("Default smoke report uses fixtures and fake/mock providers only.")
    lines.append("")
    return "\n".join(lines)


def _smoke_asr() -> dict[str, Any]:
    item = load_generated_manifest("librispeech")["items"][0]
    transcript = FakeASR().transcribe(b"", expected_text=item["transcript"])
    return {
        "status": "passed" if transcript == item["transcript"] else "failed",
        "provider": "fake",
        "fixture_id": item["id"],
        "expected": item["transcript"],
        "transcript": transcript,
    }


def _smoke_l2_arctic_fixture_asr() -> dict[str, Any]:
    items = load_generated_manifest("l2_arctic")["items"]
    pairs = [
        (item["transcript"], FakeASR().transcribe(b"", expected_text=item["transcript"]))
        for item in items[:5]
    ]
    average_wer = sum(word_error_rate(expected, transcript) for expected, transcript in pairs) / len(pairs)
    return {
        "status": "passed" if average_wer == 0 else "failed",
        "provider": "fake",
        "count": len(pairs),
        "average_wer": average_wer,
        "manual_annotation_rate": _manual_annotation_rate(items),
    }


def _smoke_grammar() -> dict[str, Any]:
    item = load_text_fixture("grammar_expression_errors")["items"][0]
    correction = grammar_service.check(
        scenario_id=item["scenario_id"],
        user_text=item["original_text"],
        conversation_context=[],
    )
    return {
        "status": "passed" if correction.corrected_text else "failed",
        "fixture_id": item["id"],
        "issue_count": len(correction.issues),
        "corrected_text": correction.corrected_text,
    }


def _smoke_pronunciation() -> dict[str, Any]:
    item = load_generated_manifest("speechocean762")["items"][0]
    assessment = MockPronunciationProvider().assess(fixture_id=item["id"])
    return {
        "status": "passed" if assessment is not None else "failed",
        "provider": "mock",
        "fixture_id": item["id"],
        "overall": assessment.overall if assessment else None,
        "issue_count": len(assessment.issues) if assessment else 0,
    }


def _smoke_dialogue_fixture() -> dict[str, Any]:
    sample = load_text_fixture("dialogue_samples")["samples"][0]
    turns = sample["turns"]
    user_turns = [turn for turn in turns if turn["speaker"] == "user"]
    ai_turns = [turn for turn in turns if turn["speaker"] == "ai"]
    return {
        "status": "passed" if user_turns and ai_turns else "failed",
        "fixture_id": sample["id"],
        "scenario_id": sample["scenario_id"],
        "turn_count": len(turns),
    }


def _smoke_real_llm(status: dict[str, object]) -> dict[str, Any]:
    if status["llm_provider"] in {"fake", "none", "disabled"}:
        return {"status": "skipped", "provider": status["llm_provider"], "reason": "LLM_PROVIDER is not real"}
    started = time.perf_counter()
    try:
        client = create_llm_client_from_env()
        if client is None:
            return {"status": "skipped", "provider": status["llm_provider"], "reason": "LLM client disabled"}
        content = client.complete(
            [
                LLMMessage(
                    role="system",
                    content="Reply with one short English sentence.",
                ),
                LLMMessage(
                    role="user",
                    content="Say hello as an English speaking coach.",
                ),
            ]
        )
        latency_ms = _elapsed_ms(started)
        return {
            "status": "passed" if content.strip() else "failed",
            "provider": status["llm_provider"],
            "model": status.get("llm_model"),
            "latency_ms": latency_ms,
            "response_chars": len(content),
        }
    except Exception as exc:  # pragma: no cover - real provider smoke is environment-dependent.
        return _failed_real_check(
            provider=str(status["llm_provider"]),
            started=started,
            exc=exc,
        )


def _smoke_real_asr(status: dict[str, object]) -> dict[str, Any]:
    if status["asr_provider"] in {"fake", "none", "disabled"}:
        return {"status": "skipped", "provider": status["asr_provider"], "reason": "ASR_PROVIDER is not real"}
    item = load_generated_manifest("librispeech")["items"][0]
    audio_path = resolve_fixture_audio(item["audio_file"])
    started = time.perf_counter()
    try:
        from backend.app.services.asr import create_asr_provider

        provider = create_asr_provider()
        transcript = provider.transcribe_file(audio_path)
        latency_ms = _elapsed_ms(started)
        wer = word_error_rate(item["transcript"], transcript)
        return {
            "status": "passed" if transcript.strip() else "failed",
            "provider": status["asr_provider"],
            "fixture_id": item["id"],
            "latency_ms": latency_ms,
            "wer": wer,
            "transcript": transcript,
        }
    except Exception as exc:  # pragma: no cover - real provider smoke is environment-dependent.
        return _failed_real_check(
            provider=str(status["asr_provider"]),
            started=started,
            exc=exc,
            fixture_id=item["id"],
        )


def _smoke_real_l2_arctic_asr(status: dict[str, object]) -> dict[str, Any]:
    if status["asr_provider"] in {"fake", "none", "disabled"}:
        return {"status": "skipped", "provider": status["asr_provider"], "reason": "ASR_PROVIDER is not real"}
    items = load_generated_manifest("l2_arctic")["items"]
    limit = max(1, int(os.environ.get("SMOKE_L2_ARCTIC_LIMIT", "3") or 3))
    selected = items[:limit]
    started = time.perf_counter()
    try:
        from backend.app.services.asr import create_asr_provider

        provider = create_asr_provider()
        results: list[dict[str, Any]] = []
        for item in selected:
            audio_path = resolve_fixture_audio(item["audio_file"])
            transcript = provider.transcribe_file(audio_path)
            results.append(
                {
                    "fixture_id": item["id"],
                    "native_language": item.get("native_language"),
                    "has_manual_annotation": item.get("has_manual_annotation") is True,
                    "wer": word_error_rate(item["transcript"], transcript),
                }
            )
        average_wer = sum(item["wer"] for item in results) / len(results)
        return {
            "status": "passed" if results and all(item["wer"] <= 1.0 for item in results) else "failed",
            "provider": status["asr_provider"],
            "count": len(results),
            "latency_ms": _elapsed_ms(started),
            "average_wer": average_wer,
            "manual_annotation_rate": _manual_annotation_rate(items),
            "results": results,
        }
    except Exception as exc:  # pragma: no cover - real provider smoke is environment-dependent.
        return _failed_real_check(
            provider=str(status["asr_provider"]),
            started=started,
            exc=exc,
        )


def _smoke_real_pronunciation(status: dict[str, object]) -> dict[str, Any]:
    if status["pronunciation_provider"] in {"mock", "none", "disabled"}:
        return {
            "status": "skipped",
            "provider": status["pronunciation_provider"],
            "reason": "PRON_PROVIDER is not real",
        }
    item = load_generated_manifest("speechocean762")["items"][0]
    started = time.perf_counter()
    try:
        from backend.app.services.pronunciation import create_pronunciation_provider

        provider = create_pronunciation_provider()
        assessment = provider.assess(fixture_id=item["id"])
        latency_ms = _elapsed_ms(started)
        return {
            "status": "passed" if assessment is not None else "failed",
            "provider": status["pronunciation_provider"],
            "fixture_id": item["id"],
            "latency_ms": latency_ms,
            "overall": assessment.overall if assessment else None,
            "issue_count": len(assessment.issues) if assessment else 0,
        }
    except Exception as exc:  # pragma: no cover - real provider smoke is environment-dependent.
        return _failed_real_check(
            provider=str(status["pronunciation_provider"]),
            started=started,
            exc=exc,
            fixture_id=item["id"],
        )


def _failed_real_check(
    *,
    provider: str,
    started: float,
    exc: Exception,
    fixture_id: str | None = None,
) -> dict[str, Any]:
    payload = {
        "status": "failed",
        "provider": provider,
        "latency_ms": _elapsed_ms(started),
        "error_type": type(exc).__name__,
        "error": _safe_error_message(exc),
    }
    if fixture_id is not None:
        payload["fixture_id"] = fixture_id
    return payload


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000.0, 1)


def _safe_error_message(exc: Exception) -> str:
    message = str(exc)
    message = re.sub(r"https?://\S+", "[redacted-url]", message)
    message = re.sub(r"wss?://\S+", "[redacted-url]", message)
    return message[:240]


def _provider_markdown_lines(status: object) -> list[str]:
    if not isinstance(status, dict):
        return []
    return [
        "## Providers",
        "",
        f"- LLM: {status.get('llm_provider')} ({status.get('llm_model') or 'no model'})",
        f"- ASR: {status.get('asr_provider')}",
        f"- Pronunciation: {status.get('pronunciation_provider')}",
        f"- TTS: {status.get('tts_provider')}",
        "",
    ]


def _check_line(label: str, check: object) -> list[str]:
    if not isinstance(check, dict):
        return []
    suffix = f" ({check['provider']})" if "provider" in check else ""
    detail = ""
    if "average_wer" in check:
        detail = f", avg WER {float(check['average_wer']):.4f}"
    if "count" in check:
        detail = f"{detail}, count {check['count']}"
    return [f"- {label}: {check.get('status')}{suffix}{detail}"]


def _format_latency(value: object) -> str:
    if value is None:
        return "not measured"
    return f"{float(value):.1f} ms"


def _manual_annotation_rate(items: list[dict[str, Any]]) -> float:
    if not items:
        return 0.0
    annotated = sum(1 for item in items if item.get("has_manual_annotation") is True)
    return annotated / len(items)
