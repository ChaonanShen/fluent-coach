from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TurnSpeaker(StrEnum):
    AI = "ai"
    USER = "user"


class SessionStatus(StrEnum):
    ACTIVE = "active"
    ENDED = "ended"


class SessionTitleSource(StrEnum):
    AUTO = "auto"
    MANUAL = "manual"
    FALLBACK = "fallback"


class Scenario(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    ai_role: str = Field(min_length=1)
    user_role: str = Field(min_length=1)
    opening_line: str = Field(min_length=1)
    conversation_goals: list[str] = Field(min_length=1)
    target_expressions: list[str] = Field(default_factory=list)
    correction_focus: list[str] = Field(default_factory=list)
    summary_rubric: dict[str, str] = Field(default_factory=dict)


class Turn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: str(uuid4()))
    session_id: str = Field(min_length=1)
    speaker: TurnSpeaker
    text: str = Field(min_length=1)
    created_at: datetime = Field(default_factory=utc_now)
    mode: Literal["text", "audio"] = "text"
    audio_path: str | None = None
    asr_confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class KnownInfoSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    kind: Literal["text", "pdf"]
    text_preview: str | None = Field(default=None, max_length=500)
    char_count: int = Field(default=0, ge=0)


class Session(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: str(uuid4()))
    scenario_id: str = Field(min_length=1)
    custom_scenario: Scenario | None = None
    title: str | None = Field(default=None, min_length=1, max_length=100)
    title_source: SessionTitleSource | None = None
    scenario_name_snapshot: str | None = Field(default=None, min_length=1, max_length=100)
    custom_prompt: str | None = Field(default=None, min_length=1, max_length=2000)
    known_info_text: str | None = Field(default=None, max_length=12000)
    known_info_sources: list[KnownInfoSource] = Field(default_factory=list)
    status: SessionStatus = SessionStatus.ACTIVE
    created_at: datetime = Field(default_factory=utc_now)
    ended_at: datetime | None = None
    turns: list[Turn] = Field(default_factory=list)

    @field_validator("known_info_text", mode="before")
    @classmethod
    def normalize_known_info_text(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, str):
            normalized = " ".join(value.split())
            return normalized or None
        return value

    def add_turn(
        self,
        *,
        speaker: TurnSpeaker,
        text: str,
        mode: Literal["text", "audio"] = "text",
        audio_path: str | None = None,
        asr_confidence: float | None = None,
    ) -> Turn:
        turn = Turn(
            session_id=self.id,
            speaker=speaker,
            text=text,
            mode=mode,
            audio_path=audio_path,
            asr_confidence=asr_confidence,
        )
        self.turns.append(turn)
        return turn

    def end(self) -> None:
        self.status = SessionStatus.ENDED
        self.ended_at = utc_now()

    def rename(self, title: str, *, source: SessionTitleSource = SessionTitleSource.MANUAL) -> None:
        self.title = " ".join(title.split())
        self.title_source = source
