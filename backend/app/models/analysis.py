from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class CorrectionTiming(StrEnum):
    IMMEDIATE_LIGHT = "immediate_light"
    AFTER_TURN = "after_turn"
    DELAYED_SUMMARY = "delayed_summary"


class GrammarSeverity(StrEnum):
    MINOR = "minor"
    MAJOR = "major"


class AnalysisStage(StrEnum):
    ASR = "asr"
    GRAMMAR = "grammar"
    PRONUNCIATION = "pronunciation"
    TTS = "tts"


class AnalysisErrorSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class MistakeType(StrEnum):
    GRAMMAR = "grammar"
    EXPRESSION = "expression"
    PRONUNCIATION = "pronunciation"


class MistakeSourceStage(StrEnum):
    GRAMMAR = "grammar"
    EXPRESSION = "expression"
    PRONUNCIATION = "pronunciation"


class GrammarIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error_type: str = Field(min_length=1)
    original_span: str = Field(min_length=1)
    corrected_span: str = Field(min_length=1)
    severity: GrammarSeverity
    explanation_zh: str = Field(min_length=1)


class GrammarCorrection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: str(uuid4()))
    scenario_id: str = Field(min_length=1)
    user_text: str = Field(min_length=1)
    corrected_text: str = Field(min_length=1)
    better_expression: str | None = None
    issues: list[GrammarIssue] = Field(default_factory=list)
    overall_severity: GrammarSeverity
    correction_timing: CorrectionTiming
    naturalness_reason_zh: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class PhonemeScore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phoneme: str = Field(min_length=1)
    accuracy: float = Field(ge=0.0, le=100.0)
    issue: str | None = None


class PronunciationWordScore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    word: str = Field(min_length=1)
    accuracy: float = Field(ge=0.0, le=100.0)
    fluency: float | None = Field(default=None, ge=0.0, le=100.0)
    phonemes: list[PhonemeScore] = Field(default_factory=list)
    issue: str | None = None


class PronunciationIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str = Field(min_length=1)
    target: str = Field(min_length=1)
    message_zh: str = Field(min_length=1)
    severity: GrammarSeverity = GrammarSeverity.MINOR


class PronunciationAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: str(uuid4()))
    provider: str = Field(min_length=1)
    reference_text: str = Field(min_length=1)
    audio_file: str | None = None
    overall: float = Field(ge=0.0, le=100.0)
    accuracy: float = Field(ge=0.0, le=100.0)
    fluency: float = Field(ge=0.0, le=100.0)
    prosody: float | None = Field(default=None, ge=0.0, le=100.0)
    completeness: float | None = Field(default=None, ge=0.0, le=100.0)
    words: list[PronunciationWordScore] = Field(default_factory=list)
    issues: list[PronunciationIssue] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)


class SessionSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: str(uuid4()))
    session_id: str = Field(min_length=1)
    grammar_score: float | None = Field(default=None, ge=0.0, le=100.0)
    pronunciation_score: float | None = Field(default=None, ge=0.0, le=100.0)
    fluency_score: float | None = Field(default=None, ge=0.0, le=100.0)
    vocabulary_score: float | None = Field(default=None, ge=0.0, le=100.0)
    task_completion_rate: float = Field(ge=0.0, le=1.0)
    top_issues: list[str] = Field(default_factory=list)
    next_drills: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)


class MistakeItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: str(uuid4()))
    type: MistakeType
    session_id: str | None = None
    turn_id: str | None = None
    source_stage: MistakeSourceStage | None = None
    source_id: str | None = None
    subtype: str | None = None
    severity: GrammarSeverity | None = None
    tags: list[str] = Field(default_factory=list)
    wrong: str = Field(min_length=1)
    correct: str = Field(min_length=1)
    explanation_zh: str = Field(min_length=1)
    practice_sentence: str = Field(min_length=1)
    word: str | None = None
    phoneme: str | None = None
    mastery: float = Field(default=0.0, ge=0.0, le=1.0)
    review_count: int = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=utc_now)
    last_seen_at: datetime | None = None
    next_review_at: datetime | None = None


class AnalysisError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: str(uuid4()))
    stage: AnalysisStage
    code: str = Field(min_length=1)
    user_message_zh: str = Field(min_length=1)
    severity: AnalysisErrorSeverity
    fallback_applied: bool
    provider: str | None = None
    raw_code: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
