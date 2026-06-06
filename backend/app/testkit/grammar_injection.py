from __future__ import annotations

import re
from typing import Any

from backend.app.testkit.grammar_cases import GrammarErrorCase, grammar_case_sequence


ERROR_TYPE_ALIASES: dict[str, set[str]] = {
    "subject_verb_agreement": {"subject_verb_agreement", "agreement", "verb_agreement", "subject verb agreement"},
    "plural_noun": {"plural_noun", "plural", "pluralization", "noun_number", "number", "singular_plural"},
    "verb_tense": {"verb_tense", "verb_tense_error", "tense", "tense_mismatch", "past_tense", "verb tense"},
    "article": {"article", "articles", "determiner", "missing_article", "article_missing"},
    "gerund": {"gerund", "verb_form", "verb_form_error", "verb_form_after_'was'", "verb form"},
    "modal_verb": {"modal_verb", "modal", "modal verb"},
}


def next_error_case(scenario_id: str, index: int) -> GrammarErrorCase:
    if index < 0:
        raise ValueError("index must be non-negative")
    return grammar_case_sequence(scenario_id, index + 1)[index]


def inject_errors(clean_text: str, *, scenario_id: str, index: int) -> GrammarErrorCase:
    injected = clean_text
    expected_error_types: list[str] = []
    error_spans: list[str] = []

    injected, changed = _replace_once(injected, r"\bhave\b", "has")
    if changed:
        expected_error_types.append("subject_verb_agreement")
        error_spans.append("has")

    injected, changed = _replace_once(injected, r"\byears\b", "year")
    if changed:
        expected_error_types.append("plural_noun")
        error_spans.append("year")

    for pattern, replacement in [
        (r"\bwent\b", "go"),
        (r"\bfinished\b", "finish"),
        (r"\bshared\b", "share"),
        (r"\bexplained\b", "explain"),
    ]:
        injected, changed = _replace_once(injected, pattern, replacement)
        if changed:
            expected_error_types.append("verb_tense")
            error_spans.append(replacement)
            break

    injected, changed = _remove_first_article(injected)
    if changed:
        expected_error_types.append("article")
        error_spans.append(changed)

    if not expected_error_types or injected == clean_text:
        return next_error_case(scenario_id, index)
    return GrammarErrorCase(
        scenario_id=scenario_id,
        clean_text=clean_text,
        injected_text=injected,
        expected_corrected_text=clean_text,
        expected_error_types=_dedupe(expected_error_types),
        error_spans=_dedupe(error_spans),
    )


def score_grammar_result(
    case: GrammarErrorCase,
    grammar: dict[str, Any] | None,
    asr_text: str,
) -> dict[str, object]:
    detected_types = _detected_error_types(grammar)
    expected_types = {_canonical_error_type(error_type) for error_type in case.expected_error_types}
    matched_types = {
        expected
        for expected in expected_types
        if any(_error_type_matches(expected, detected) for detected in detected_types)
    }
    corrected_text = str((grammar or {}).get("corrected_text") or "")
    return {
        "expected_error_recall": round(len(matched_types) / len(expected_types), 4) if expected_types else 0.0,
        "matched_error_types": sorted(matched_types),
        "detected_error_types": sorted(detected_types),
        "corrected_text_match": _normalize(corrected_text) == _normalize(case.expected_corrected_text),
        "asr_preserved_injected_error": _asr_preserved_injected_error(case, asr_text),
    }


def _detected_error_types(grammar: dict[str, Any] | None) -> set[str]:
    issues = (grammar or {}).get("issues") or []
    detected: set[str] = set()
    if not isinstance(issues, list):
        return detected
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        raw_type = str(issue.get("error_type") or "").strip()
        if raw_type:
            detected.add(_canonical_error_type(raw_type))
    return detected


def _error_type_matches(expected: str, detected: str) -> bool:
    expected_aliases = ERROR_TYPE_ALIASES.get(expected, {expected})
    detected_aliases = ERROR_TYPE_ALIASES.get(detected, {detected})
    return bool(expected_aliases & detected_aliases)


def _canonical_error_type(value: str) -> str:
    normalized = _normalize_type(value)
    for canonical, aliases in ERROR_TYPE_ALIASES.items():
        if normalized in {_normalize_type(alias) for alias in aliases}:
            return canonical
    return normalized


def _normalize_type(value: str) -> str:
    return "_".join(value.strip().lower().replace("-", " ").split())


def _asr_preserved_injected_error(case: GrammarErrorCase, asr_text: str) -> bool:
    normalized_asr = _normalize(asr_text)
    spans = [_normalize(span) for span in case.error_spans if span.strip()]
    if not spans:
        return _normalize(case.injected_text) == normalized_asr
    return any(_contains_phrase(normalized_asr, span) for span in spans)


def _normalize(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9\s]", "", value.lower()).split())


def _contains_phrase(text: str, phrase: str) -> bool:
    return re.search(rf"(^|\s){re.escape(phrase)}($|\s)", text) is not None


def _replace_once(text: str, pattern: str, replacement: str) -> tuple[str, bool]:
    updated, count = re.subn(pattern, replacement, text, count=1, flags=re.IGNORECASE)
    return updated, count > 0


def _remove_first_article(text: str) -> tuple[str, str | None]:
    match = re.search(r"\ba\s+([a-zA-Z]{3,})\b", text)
    if match is None:
        return text, None
    return text[: match.start()] + match.group(1) + text[match.end() :], match.group(1)


def _dedupe(values: list[str]) -> list[str]:
    deduped: list[str] = []
    for value in values:
        if value not in deduped:
            deduped.append(value)
    return deduped
