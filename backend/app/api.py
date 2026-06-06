from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from backend.app.models import (
    AnalysisError,
    GrammarCorrection,
    MistakeItem,
    PronunciationAssessment,
    Scenario,
    Session,
    SessionSummary,
    Turn,
)


class ScenarioListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenarios: list[Scenario]


class CreateSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str = Field(min_length=1)
    custom_topic: str | None = Field(default=None, min_length=3, max_length=160)
    custom_prompt: str | None = Field(default=None, min_length=3, max_length=2000)
    custom_name: str | None = Field(default=None, min_length=1, max_length=100)


class UpdateSessionTitleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=100)


class SessionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session: Session
    scenario: Scenario
    opening_line: str
    conversation_goals: list[str]
    target_expressions: list[str]


class GrammarCheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str = Field(min_length=1)
    user_text: str = Field(min_length=1)
    conversation_context: list[str] = Field(default_factory=list)


class TextTurnRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1)


class TextTurnResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session: Session
    user_turn: Turn
    ai_turn: Turn
    current_goal: str
    next_intent: str
    grammar_result: GrammarCorrection


class PronunciationAssessRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reference_text: str | None = Field(default=None, min_length=1)
    audio_file: str | None = Field(default=None, min_length=1)
    fixture_id: str | None = Field(default=None, min_length=1)
    session_id: str | None = Field(default=None, min_length=1)


class PronunciationUploadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reference_text: str = Field(min_length=1)
    audio_base64: str = Field(min_length=1)
    mime_type: str | None = Field(default=None, min_length=1)
    session_id: str | None = Field(default=None, min_length=1)


class PronunciationPracticeUploadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reference_text: str | None = Field(default=None, min_length=1)
    audio_base64: str = Field(min_length=1)
    mime_type: str | None = Field(default=None, min_length=1)


class MistakeListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mistakes: list[MistakeItem]


class MistakeBookRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    title: str
    scenario_id: str
    scenario_name: str
    status: str
    created_at: datetime
    ended_at: datetime | None
    mistake_count: int
    grammar_count: int
    expression_count: int
    pronunciation_count: int
    lowest_mastery: float | None
    due_count: int
    summary: SessionSummary | None


class MistakeBookListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    books: list[MistakeBookRecord]


class MistakeTurnGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    turn: Turn | None
    mistakes: list[MistakeItem]


class MistakeBookDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record: MistakeBookRecord
    turn_groups: list[MistakeTurnGroup]


class DeleteMistakeBooksRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_ids: list[str] = Field(default_factory=list)


class DeleteResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deleted_count: int = Field(ge=0)


class SessionAnalysisResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    grammar_results: list[GrammarCorrection]
    pronunciation_results: list[PronunciationAssessment]
    errors: list[AnalysisError]


class ProgressPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    scenario_id: str
    created_at: str
    grammar_score: float | None
    pronunciation_score: float | None
    fluency_score: float | None
    vocabulary_score: float | None
    task_completion_rate: float


class ProgressResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_count: int
    average_grammar_score: float | None
    average_pronunciation_score: float | None
    average_fluency_score: float | None
    average_vocabulary_score: float | None
    average_task_completion_rate: float | None
    trend: list[ProgressPoint]


class TTSRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1)


class TTSResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    text: str
    audio_url: str | None
    audio_base64: str | None = None
    mime_type: str | None = None
    fallback_applied: bool
