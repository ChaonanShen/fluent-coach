from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.app.core.fixtures import load_generated_manifest
from backend.app.eval.metrics import corpus_gleu, corpus_wer, mean_absolute_error, pearson_correlation
from backend.app.services.asr import fake_asr
from backend.app.services.grammar import grammar_service
from backend.app.services.pronunciation import MockPronunciationProvider


def run_all_evaluations() -> dict[str, Any]:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "asr": evaluate_asr(),
        "grammar": evaluate_grammar(),
        "pronunciation": evaluate_pronunciation(),
        "summary": {
            "default_provider_mode": "fixture_fake",
            "external_services_used": False,
        },
    }


def evaluate_asr() -> dict[str, Any]:
    librispeech = load_generated_manifest("librispeech")["items"]
    l2_arctic = load_generated_manifest("l2_arctic")["items"]
    clean_pairs = [
        (item["transcript"], fake_asr.transcribe(b"", expected_text=item["transcript"]))
        for item in librispeech
    ]
    l2_pairs = [
        (item["transcript"], fake_asr.transcribe(b"", expected_text=item["transcript"]))
        for item in l2_arctic
    ]
    return {
        "librispeech_count": len(clean_pairs),
        "librispeech_wer": corpus_wer(clean_pairs),
        "l2_arctic_count": len(l2_pairs),
        "l2_arctic_wer": corpus_wer(l2_pairs),
        "l2_arctic_native_language_counts": _native_language_counts(l2_arctic),
        "l2_arctic_manual_annotation_rate": _manual_annotation_rate(l2_arctic),
    }


def evaluate_grammar() -> dict[str, Any]:
    jfleg = load_generated_manifest("jfleg")["items"]
    candidates: list[tuple[str, list[str]]] = []
    schema_pass = 0
    for item in jfleg:
        correction = grammar_service.check(
            scenario_id="interview",
            user_text=item["source"],
            conversation_context=[],
        )
        if correction.corrected_text:
            schema_pass += 1
        candidates.append((correction.corrected_text, item["references"]))
    return {
        "jfleg_count": len(jfleg),
        "schema_pass_rate": schema_pass / len(jfleg) if jfleg else 0.0,
        "gleu": corpus_gleu(candidates),
    }


def evaluate_pronunciation() -> dict[str, Any]:
    provider = MockPronunciationProvider()
    items = load_generated_manifest("speechocean762")["items"]
    truth: list[float] = []
    predicted: list[float] = []
    returned = 0
    for item in items:
        assessment = provider.assess(fixture_id=item["id"])
        if assessment is None:
            continue
        returned += 1
        truth.append(float(item["sentence_scores"]["total"]) * 10)
        predicted.append(assessment.overall)
    return {
        "speechocean_count": len(items),
        "provider_return_rate": returned / len(items) if items else 0.0,
        "sentence_total_correlation": pearson_correlation(truth, predicted),
        "sentence_total_mae": mean_absolute_error(truth, predicted),
    }


def render_markdown(report: dict[str, Any]) -> str:
    asr = report["asr"]
    grammar = report["grammar"]
    pronunciation = report["pronunciation"]
    lines = [
        "# Evaluation Report",
        "",
        f"Generated at: `{report['generated_at']}`",
        "",
        "## ASR",
        "",
        f"- LibriSpeech count: {asr['librispeech_count']}",
        f"- LibriSpeech WER: {asr['librispeech_wer']:.4f}",
        f"- L2-ARCTIC count: {asr['l2_arctic_count']}",
        f"- L2-ARCTIC WER: {asr['l2_arctic_wer']:.4f}",
        f"- L2-ARCTIC manual annotation rate: {asr['l2_arctic_manual_annotation_rate']:.4f}",
        f"- L2-ARCTIC native languages: {_format_counts(asr['l2_arctic_native_language_counts'])}",
        "",
        "## Grammar",
        "",
        f"- JFLEG count: {grammar['jfleg_count']}",
        f"- Schema pass rate: {grammar['schema_pass_rate']:.4f}",
        f"- GLEU: {grammar['gleu']:.4f}",
        "",
        "## Pronunciation",
        "",
        f"- SpeechOcean count: {pronunciation['speechocean_count']}",
        f"- Provider return rate: {pronunciation['provider_return_rate']:.4f}",
        f"- Sentence total correlation: {pronunciation['sentence_total_correlation']:.4f}",
        f"- Sentence total MAE: {pronunciation['sentence_total_mae']:.4f}",
        "",
        "Default evaluation uses fixture-backed fake providers and does not call external services.",
        "",
    ]
    return "\n".join(lines)


def _native_language_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        language = str(item.get("native_language") or "unknown")
        counts[language] = counts.get(language, 0) + 1
    return dict(sorted(counts.items()))


def _manual_annotation_rate(items: list[dict[str, Any]]) -> float:
    if not items:
        return 0.0
    annotated = sum(1 for item in items if item.get("has_manual_annotation") is True)
    return annotated / len(items)


def _format_counts(counts: dict[str, int]) -> str:
    return ", ".join(f"{name}={count}" for name, count in counts.items()) if counts else "none"
