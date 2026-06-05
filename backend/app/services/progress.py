from __future__ import annotations

from backend.app.api import ProgressPoint, ProgressResponse
from backend.app.services.scenarios import resolve_session_scenario
from backend.app.services.storage import SQLiteLogStore, log_store
from backend.app.services.summary import summary_service


class ProgressService:
    def __init__(self, storage: SQLiteLogStore = log_store) -> None:
        self.storage = storage

    def get_progress(self) -> ProgressResponse:
        points: list[ProgressPoint] = []
        for session in sorted(self.storage.list_sessions(), key=lambda item: item.created_at):
            scenario = resolve_session_scenario(session)
            if scenario is None:
                continue
            summary = summary_service.summarize(session=session, scenario=scenario)
            points.append(
                ProgressPoint(
                    session_id=session.id,
                    scenario_id=session.scenario_id,
                    created_at=session.created_at.isoformat(),
                    grammar_score=summary.grammar_score,
                    pronunciation_score=summary.pronunciation_score,
                    fluency_score=summary.fluency_score,
                    vocabulary_score=summary.vocabulary_score,
                    task_completion_rate=summary.task_completion_rate,
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


progress_service = ProgressService()
