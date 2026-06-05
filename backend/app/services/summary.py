from __future__ import annotations

from backend.app.models import (
    GrammarSeverity,
    PronunciationAssessment,
    Scenario,
    Session,
    SessionSummary,
    TurnSpeaker,
)
from backend.app.services.analysis import analysis_store
from backend.app.services.grammar import grammar_service


class SummaryService:
    def summarize(self, *, session: Session, scenario: Scenario) -> SessionSummary:
        user_turns = [turn for turn in session.turns if turn.speaker == TurnSpeaker.USER]
        corrections = analysis_store.grammar_results(session.id)
        if not corrections:
            corrections = [
                grammar_service.check(
                    scenario_id=scenario.id,
                    user_text=turn.text,
                    conversation_context=[],
                )
                for turn in user_turns
            ]
        issues = [issue for correction in corrections for issue in correction.issues]
        major_count = sum(1 for issue in issues if issue.severity == GrammarSeverity.MAJOR)
        minor_count = len(issues) - major_count
        grammar_score = max(0.0, 100.0 - major_count * 15.0 - minor_count * 5.0)

        task_completion_rate = 0.0
        if scenario.conversation_goals:
            task_completion_rate = min(1.0, len(user_turns) / len(scenario.conversation_goals))

        target_hits = self._target_expression_hits(scenario=scenario, user_turn_texts=[turn.text for turn in user_turns])
        vocabulary_score = min(100.0, 70.0 + target_hits * 6.0) if user_turns else None
        fluency_score = min(100.0, 65.0 + len(user_turns) * 5.0) if user_turns else None
        pronunciation_results = analysis_store.pronunciation_results(session.id)
        pronunciation_score = self._pronunciation_score(pronunciation_results)
        top_issues = [
            *self._top_issues(issues),
            *self._top_pronunciation_issues(pronunciation_results),
        ][:5]

        return SessionSummary(
            session_id=session.id,
            grammar_score=grammar_score if user_turns else None,
            pronunciation_score=pronunciation_score,
            fluency_score=fluency_score,
            vocabulary_score=vocabulary_score,
            task_completion_rate=task_completion_rate,
            top_issues=top_issues,
            next_drills=self._next_drills(top_issues=top_issues, scenario=scenario),
        )

    def _target_expression_hits(self, *, scenario: Scenario, user_turn_texts: list[str]) -> int:
        joined = " ".join(user_turn_texts).lower()
        return sum(1 for expression in scenario.target_expressions if expression.lower().rstrip(".") in joined)

    def _top_issues(self, issues: list[object]) -> list[str]:
        counts: dict[str, int] = {}
        for issue in issues:
            error_type = getattr(issue, "error_type")
            counts[error_type] = counts.get(error_type, 0) + 1
        return [
            error_type
            for error_type, _count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:5]
        ]

    def _pronunciation_score(self, assessments: list[PronunciationAssessment]) -> float | None:
        if not assessments:
            return None
        return assessments[-1].overall

    def _top_pronunciation_issues(self, assessments: list[PronunciationAssessment]) -> list[str]:
        counts: dict[str, int] = {}
        for assessment in assessments:
            for issue in assessment.issues:
                key = f"pronunciation: {issue.target}"
                counts[key] = counts.get(key, 0) + 1
        return [
            issue
            for issue, _count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:5]
        ]

    def _next_drills(self, *, top_issues: list[str], scenario: Scenario) -> list[str]:
        if top_issues:
            return [self._drill_for_issue(issue) for issue in top_issues[:3]]
        return [f"Practice using: {expression}" for expression in scenario.target_expressions[:3]]

    def _drill_for_issue(self, issue: str) -> str:
        if issue.startswith("pronunciation:"):
            target = issue.split(":", 1)[1].strip()
            return f"Practice pronouncing {target} in one short sentence."
        return f"Review {issue.replace('_', ' ')} in one short answer."


summary_service = SummaryService()
