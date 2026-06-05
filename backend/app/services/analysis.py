from __future__ import annotations

from collections import defaultdict

from backend.app.models import AnalysisError, GrammarCorrection
from backend.app.services.storage import log_store


class AnalysisStore:
    def __init__(self) -> None:
        self._grammar_results: dict[str, list[GrammarCorrection]] = defaultdict(list)
        self._errors: dict[str, list[AnalysisError]] = defaultdict(list)

    def add_grammar_result(self, session_id: str, correction: GrammarCorrection) -> None:
        self._grammar_results[session_id].append(correction)

    def add_error(self, session_id: str, error: AnalysisError) -> None:
        self._errors[session_id].append(error)
        log_store.save_analysis_error(error)

    def grammar_results(self, session_id: str) -> list[GrammarCorrection]:
        return list(self._grammar_results.get(session_id, []))

    def errors(self, session_id: str) -> list[AnalysisError]:
        return list(self._errors.get(session_id, []))

    def clear(self) -> None:
        self._grammar_results.clear()
        self._errors.clear()


analysis_store = AnalysisStore()
