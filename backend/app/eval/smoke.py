from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.app.core.fixtures import load_generated_manifest, load_text_fixture
from backend.app.services.asr import FakeASR
from backend.app.services.grammar import grammar_service
from backend.app.services.pronunciation import MockPronunciationProvider


def run_fixture_smoke_report() -> dict[str, Any]:
    asr = _smoke_asr()
    grammar = _smoke_grammar()
    pronunciation = _smoke_pronunciation()
    dialogue = _smoke_dialogue_fixture()
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "fixture_fake",
        "external_services_used": False,
        "checks": {
            "asr": asr,
            "grammar": grammar,
            "pronunciation": pronunciation,
            "dialogue_fixture": dialogue,
            "ui_manual": {
                "status": "not_run",
                "checklist": [
                    "Start a session from the browser UI.",
                    "Record one voice turn and confirm asr.final plus reply.text appear.",
                    "Record Read Aloud and confirm pronunciation score appears.",
                    "End the session and confirm summary renders.",
                ],
            },
        },
        "latency_ms": {
            "end_turn_to_asr_final": None,
            "asr_final_to_reply_text": None,
            "reply_text_to_tts_start": None,
            "pronunciation_upload_to_result": None,
        },
    }


def render_smoke_markdown(report: dict[str, Any]) -> str:
    checks = report["checks"]
    latency = report["latency_ms"]
    lines = [
        "# Smoke Report",
        "",
        f"Generated at: `{report['generated_at']}`",
        f"Mode: `{report['mode']}`",
        f"External services used: `{str(report['external_services_used']).lower()}`",
        "",
        "## Checks",
        "",
        f"- ASR: {checks['asr']['status']} ({checks['asr']['provider']})",
        f"- Grammar: {checks['grammar']['status']}",
        f"- Pronunciation: {checks['pronunciation']['status']} ({checks['pronunciation']['provider']})",
        f"- Dialogue fixture: {checks['dialogue_fixture']['status']}",
        f"- UI manual: {checks['ui_manual']['status']}",
        "",
        "## Latency",
        "",
        f"- end_turn -> asr.final: {_format_latency(latency['end_turn_to_asr_final'])}",
        f"- asr.final -> reply.text: {_format_latency(latency['asr_final_to_reply_text'])}",
        f"- reply.text -> tts_start: {_format_latency(latency['reply_text_to_tts_start'])}",
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


def _format_latency(value: object) -> str:
    if value is None:
        return "not measured"
    return f"{float(value):.1f} ms"
