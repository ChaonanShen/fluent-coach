from __future__ import annotations

from functools import lru_cache
from typing import Any

from backend.app.core.fixtures import load_text_fixture
from backend.app.models import (
    CorrectionTiming,
    GrammarCorrection,
    GrammarIssue,
    GrammarSeverity,
)


@lru_cache(maxsize=1)
def _grammar_items() -> tuple[dict[str, Any], ...]:
    payload = load_text_fixture("grammar_expression_errors")
    return tuple(payload["items"])


def _normalize(text: str) -> str:
    return " ".join(text.strip().lower().split())


class GrammarCorrectionService:
    def check(
        self,
        *,
        scenario_id: str,
        user_text: str,
        conversation_context: list[str] | None = None,
    ) -> GrammarCorrection:
        del conversation_context
        normalized_text = _normalize(user_text)
        for item in _grammar_items():
            if item["scenario_id"] != scenario_id:
                continue
            if _normalize(item["original_text"]) != normalized_text:
                continue
            return self._from_fixture_item(item)

        return GrammarCorrection(
            scenario_id=scenario_id,
            user_text=user_text,
            corrected_text=user_text,
            better_expression=None,
            issues=[],
            overall_severity=GrammarSeverity.MINOR,
            correction_timing=CorrectionTiming.DELAYED_SUMMARY,
        )

    def _from_fixture_item(self, item: dict[str, Any]) -> GrammarCorrection:
        return GrammarCorrection(
            scenario_id=item["scenario_id"],
            user_text=item["original_text"],
            corrected_text=item["expected_corrected_text"],
            better_expression=item.get("better_expression"),
            issues=[
                GrammarIssue(
                    error_type=error_type,
                    original_span=item["error_span"],
                    corrected_span=item["expected_corrected_text"],
                    severity=item["severity"],
                    explanation_zh=item["explanation_zh"],
                )
                for error_type in item["error_types"]
            ],
            overall_severity=item["severity"],
            correction_timing=item["correction_timing"],
            naturalness_reason_zh=item.get("naturalness_reason_zh"),
        )


grammar_service = GrammarCorrectionService()
