from __future__ import annotations

from backend.app.models import (
    GrammarCorrection,
    MistakeItem,
    MistakeType,
    PronunciationAssessment,
)
from backend.app.services.storage import SQLiteLogStore, log_store


class MistakeService:
    def __init__(self, storage: SQLiteLogStore = log_store) -> None:
        self.storage = storage

    def list(self) -> list[MistakeItem]:
        return self.storage.list_mistake_items()

    def get(self, mistake_id: str) -> MistakeItem | None:
        return self.storage.get_mistake_item(mistake_id)

    def add_from_grammar(self, correction: GrammarCorrection) -> list[MistakeItem]:
        created: list[MistakeItem] = []
        for issue in correction.issues:
            mistake = MistakeItem(
                type=MistakeType.GRAMMAR,
                wrong=issue.original_span,
                correct=correction.corrected_text,
                explanation_zh=issue.explanation_zh,
                practice_sentence=correction.corrected_text,
                mastery=0.1,
            )
            created.append(self._upsert_or_merge(mistake))

        if correction.better_expression and correction.better_expression != correction.corrected_text:
            mistake = MistakeItem(
                type=MistakeType.EXPRESSION,
                wrong=correction.user_text,
                correct=correction.better_expression,
                explanation_zh=correction.naturalness_reason_zh or "这个表达在当前场景下可以更自然、更具体。",
                practice_sentence=correction.better_expression,
                mastery=0.1,
            )
            created.append(self._upsert_or_merge(mistake))
        return created

    def add_from_pronunciation(self, assessment: PronunciationAssessment) -> list[MistakeItem]:
        created: list[MistakeItem] = []
        for issue in assessment.issues:
            mistake = MistakeItem(
                type=MistakeType.PRONUNCIATION,
                wrong=issue.target,
                correct=issue.target,
                explanation_zh=issue.message_zh,
                practice_sentence=assessment.reference_text,
                word=issue.target,
                mastery=0.1,
            )
            created.append(self._upsert_or_merge(mistake))
        return created

    def review(self, mistake_id: str) -> MistakeItem | None:
        mistake = self.storage.get_mistake_item(mistake_id)
        if mistake is None:
            return None
        updated = mistake.model_copy(
            update={
                "review_count": mistake.review_count + 1,
                "mastery": min(1.0, mistake.mastery + 0.15),
            }
        )
        self.storage.save_mistake_item(updated)
        return updated

    def _upsert_or_merge(self, mistake: MistakeItem) -> MistakeItem:
        for existing in self.storage.list_mistake_items():
            if (
                existing.type == mistake.type
                and existing.wrong == mistake.wrong
                and existing.correct == mistake.correct
            ):
                merged = existing.model_copy(
                    update={
                        "explanation_zh": mistake.explanation_zh,
                        "practice_sentence": mistake.practice_sentence,
                    }
                )
                self.storage.save_mistake_item(merged)
                return merged
        self.storage.save_mistake_item(mistake)
        return mistake


mistake_service = MistakeService()
