from __future__ import annotations

from functools import lru_cache
from typing import Any

from backend.app.core.fixtures import load_text_fixture
from backend.app.models import (
    AnalysisStage,
    CorrectionTiming,
    GrammarCorrection,
    GrammarIssue,
    GrammarSeverity,
)
from backend.app.services.llm import LLMClient, LLMMessage, StructuredJSONCaller, create_llm_client_from_env


@lru_cache(maxsize=1)
def _grammar_items() -> tuple[dict[str, Any], ...]:
    payload = load_text_fixture("grammar_expression_errors")
    return tuple(payload["items"])


def _normalize(text: str) -> str:
    return " ".join(text.strip().lower().split())


class GrammarCorrectionService:
    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.llm_client = llm_client

    def check(
        self,
        *,
        scenario_id: str,
        user_text: str,
        conversation_context: list[str] | None = None,
    ) -> GrammarCorrection:
        normalized_text = _normalize(user_text)
        for item in _grammar_items():
            if item["scenario_id"] != scenario_id:
                continue
            if _normalize(item["original_text"]) != normalized_text:
                continue
            return self._from_fixture_item(item)

        if self.llm_client is not None:
            llm_correction = self._check_with_llm(
                scenario_id=scenario_id,
                user_text=user_text,
                conversation_context=conversation_context or [],
            )
            if llm_correction is not None:
                return llm_correction

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

    def _check_with_llm(
        self,
        *,
        scenario_id: str,
        user_text: str,
        conversation_context: list[str],
    ) -> GrammarCorrection | None:
        caller = StructuredJSONCaller(self.llm_client, stage=AnalysisStage.GRAMMAR)
        result = caller.call(
            [
                LLMMessage(
                    role="system",
                    content=(
                        "You are an English speaking coach. Return JSON only with keys: "
                        "corrected_text, better_expression, issues, overall_severity, "
                        "correction_timing, naturalness_reason_zh. "
                        "issues must be a list of objects with error_type, original_span, "
                        "corrected_span, severity, explanation_zh. "
                        "Use severity minor or major. Use correction_timing immediate_light, "
                        "after_turn, or delayed_summary. Do not over-correct natural spoken English."
                    ),
                ),
                LLMMessage(
                    role="user",
                    content=(
                        f"scenario_id: {scenario_id}\n"
                        f"conversation_context: {conversation_context[-6:]}\n"
                        f"user_text: {user_text}"
                    ),
                ),
            ]
        )
        if result.data is None:
            return None
        try:
            issues = [
                GrammarIssue(
                    error_type=str(issue.get("error_type", "expression")),
                    original_span=str(issue.get("original_span", user_text)),
                    corrected_span=str(issue.get("corrected_span", result.data.get("corrected_text", user_text))),
                    severity=str(issue.get("severity", "minor")),
                    explanation_zh=str(issue.get("explanation_zh", "建议优化这个表达。")),
                )
                for issue in result.data.get("issues", [])
                if isinstance(issue, dict)
            ]
            return GrammarCorrection(
                scenario_id=scenario_id,
                user_text=user_text,
                corrected_text=str(result.data.get("corrected_text") or user_text),
                better_expression=(
                    str(result.data["better_expression"])
                    if result.data.get("better_expression") is not None
                    else None
                ),
                issues=issues,
                overall_severity=str(result.data.get("overall_severity", "minor")),
                correction_timing=str(result.data.get("correction_timing", "delayed_summary")),
                naturalness_reason_zh=(
                    str(result.data["naturalness_reason_zh"])
                    if result.data.get("naturalness_reason_zh") is not None
                    else None
                ),
            )
        except (TypeError, ValueError):
            return None


grammar_service = GrammarCorrectionService(create_llm_client_from_env())
