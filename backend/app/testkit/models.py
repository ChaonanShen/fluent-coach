from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class TurnRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int = Field(ge=0)
    user_text: str
    asr_text: str
    expected_text: str | None = None
    audio_path: str | None = None
    reply_text: str
    grammar: dict[str, object] | None = None
    pronunciation: dict[str, object] | None = None
    errors: list[dict[str, object]] = Field(default_factory=list)
    timings_ms: dict[str, float] = Field(default_factory=dict)
    wer: float | None = Field(default=None, ge=0.0)


class LatencyStat(BaseModel):
    model_config = ConfigDict(extra="forbid")

    p50: float
    p90: float
    p95: float
    max: float
    mean: float
    count: int = Field(ge=0)


class RunRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1)
    scenario_id: str = Field(min_length=1)
    mode: str = Field(min_length=1)
    generated_at: str = Field(min_length=1)
    providers: dict[str, str | None] = Field(default_factory=dict)
    turns: list[TurnRecord] = Field(default_factory=list)
    latency_summary: dict[str, LatencyStat] = Field(default_factory=dict)
