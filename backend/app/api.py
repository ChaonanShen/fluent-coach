from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from backend.app.models import AnalysisError, GrammarCorrection, MistakeItem, Scenario, Session, Turn


class ScenarioListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenarios: list[Scenario]


class CreateSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str = Field(min_length=1)


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


class PronunciationAssessRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reference_text: str | None = Field(default=None, min_length=1)
    audio_file: str | None = Field(default=None, min_length=1)
    fixture_id: str | None = Field(default=None, min_length=1)


class MistakeListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mistakes: list[MistakeItem]


class SessionAnalysisResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    grammar_results: list[GrammarCorrection]
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
    fallback_applied: bool
