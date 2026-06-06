from __future__ import annotations

from backend.app.api import ProgressPoint, ProgressResponse
from backend.app.services.scenarios import resolve_session_scenario
from backend.app.services.storage import SQLiteLogStore, log_store


class ProgressService:
    def __init__(self, storage: SQLiteLogStore = log_store) -> None:
        self.storage = storage

    def get_progress(self) -> ProgressResponse:
        points: list[ProgressPoint] = []
        for session in sorted(self.storage.list_sessions(), key=lambda item: item.created_at):
            scenario = resolve_session_scenario(session)
            if scenario is None:
                continue
            summary = self.storage.get_session_summary(session.id)
            points.append(
                ProgressPoint(
                    session_id=session.id,
                    scenario_id=session.scenario_id,
                    created_at=session.created_at.isoformat(),
                    grammar_score=summary.grammar_score if summary else None,
                    pronunciation_score=summary.pronunciation_score if summary else None,
                    fluency_score=summary.fluency_score if summary else _fluency_fallback(len(session.turns)),
                    vocabulary_score=summary.vocabulary_score if summary else _vocabulary_fallback(len(session.turns)),
                    task_completion_rate=(
                        summary.task_completion_rate
                        if summary
                        else _task_completion_fallback(
                            user_turn_count=len([turn for turn in session.turns if turn.speaker.value == "user"]),
                            goal_count=len(scenario.conversation_goals),
                        )
                    ),
                )
            )
        return ProgressResponse(
            session_count=len(points),
            average_grammar_score=_average([point.grammar_score for point in points]),
            average_pronunciation_score=_average([point.pronunciation_score for point in points]),
            average_fluency_score=_average([point.fluency_score for point in points]),
            average_vocabulary_score=_average([point.vocabulary_score for point in points]),
            average_task_completion_rate=_average([point.task_completion_rate for point in points]),
            trend=points,
        )


def _average(values: list[float | None]) -> float | None:
    present = [value for value in values if value is not None]
    if not present:
        return None
    return sum(present) / len(present)


def _task_completion_fallback(*, user_turn_count: int, goal_count: int) -> float:
    if goal_count <= 0:
        return 0.0
    return min(1.0, user_turn_count / goal_count)


def _fluency_fallback(turn_count: int) -> float | None:
    if turn_count <= 0:
        return None
    return min(100.0, 65.0 + turn_count * 2.5)


def _vocabulary_fallback(turn_count: int) -> float | None:
    if turn_count <= 0:
        return None
    return 70.0


progress_service = ProgressService()
