from __future__ import annotations

import re

from backend.app.models import (
    GrammarCorrection,
    MistakeItem,
    MistakeSourceStage,
    MistakeType,
    PronunciationAssessment,
)
from backend.app.services.storage import SQLiteLogStore, log_store


class MistakeService:
    def __init__(self, storage: SQLiteLogStore = log_store) -> None:
        self.storage = storage

    def list(
        self,
        *,
        session_id: str | None = None,
        mistake_type: MistakeType | None = None,
        subtype: str | None = None,
    ) -> list[MistakeItem]:
        return self.storage.list_mistake_items(
            session_id=session_id,
            mistake_type=mistake_type,
            subtype=subtype,
        )

    def get(self, mistake_id: str) -> MistakeItem | None:
        return self.storage.get_mistake_item(mistake_id)

    def delete(self, mistake_id: str) -> bool:
        return self.storage.delete_mistake_item(mistake_id)

    def delete_for_session(self, session_id: str) -> int:
        return self.storage.delete_mistake_items_for_session(session_id)

    def delete_for_sessions(self, session_ids: list[str]) -> int:
        unique_session_ids = list(dict.fromkeys(session_ids))
        return self.storage.delete_mistake_items_for_sessions(unique_session_ids)

    def add_from_grammar(
        self,
        correction: GrammarCorrection,
        *,
        session_id: str | None = None,
        turn_id: str | None = None,
    ) -> list[MistakeItem]:
        created: list[MistakeItem] = []
        for issue in correction.issues:
            mistake = MistakeItem(
                type=MistakeType.GRAMMAR,
                session_id=session_id,
                turn_id=turn_id,
                source_stage=MistakeSourceStage.GRAMMAR,
                source_id=correction.id,
                subtype=issue.error_type,
                severity=issue.severity,
                tags=[correction.scenario_id, issue.error_type],
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
                session_id=session_id,
                turn_id=turn_id,
                source_stage=MistakeSourceStage.EXPRESSION,
                source_id=correction.id,
                subtype="natural_expression",
                severity=correction.overall_severity,
                tags=[correction.scenario_id, "natural_expression"],
                wrong=correction.user_text,
                correct=correction.better_expression,
                explanation_zh=correction.naturalness_reason_zh or "这个表达在当前场景下可以更自然、更具体。",
                practice_sentence=correction.better_expression,
                mastery=0.1,
            )
            created.append(self._upsert_or_merge(mistake))
        return created

    def add_from_pronunciation(
        self,
        assessment: PronunciationAssessment,
        *,
        session_id: str | None = None,
        turn_id: str | None = None,
    ) -> list[MistakeItem]:
        created: list[MistakeItem] = []
        for issue in assessment.issues:
            mistake = MistakeItem(
                type=MistakeType.PRONUNCIATION,
                session_id=session_id,
                turn_id=turn_id,
                source_stage=MistakeSourceStage.PRONUNCIATION,
                source_id=assessment.id,
                subtype=issue.kind,
                severity=issue.severity,
                tags=[issue.kind],
                wrong=issue.target,
                correct=issue.target,
                explanation_zh=issue.message_zh,
                practice_sentence=_pronunciation_practice_sentence(issue.target),
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
                and existing.session_id == mistake.session_id
                and existing.turn_id == mistake.turn_id
            ):
                merged = existing.model_copy(
                    update={
                        "explanation_zh": mistake.explanation_zh,
                        "practice_sentence": mistake.practice_sentence,
                        "source_id": mistake.source_id,
                        "subtype": mistake.subtype or existing.subtype,
                        "severity": mistake.severity or existing.severity,
                        "tags": sorted(set(existing.tags + mistake.tags)),
                        "last_seen_at": mistake.created_at,
                    }
                )
                self.storage.save_mistake_item(merged)
                return merged
        if mistake.last_seen_at is None:
            mistake = mistake.model_copy(update={"last_seen_at": mistake.created_at})
        self.storage.save_mistake_item(mistake)
        return mistake


def _pronunciation_practice_sentence(word: str) -> str:
    clean_word = re.sub(r"[^A-Za-z'-]+", " ", word).strip()
    target = clean_word or word.strip() or "this word"
    return f"Please say {target} clearly in this short sentence."


mistake_service = MistakeService()
