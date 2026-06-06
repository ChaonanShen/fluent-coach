import pytest

from backend.app.testkit.models import TurnRecord
from backend.app.testkit.report import aggregate_latency, build_run_record, percentile


def test_percentile_uses_linear_interpolation() -> None:
    assert percentile([10], 50) == 10
    assert percentile([10, 20, 30], 50) == 20
    assert percentile([10, 20, 30], 90) == 28


def test_percentile_rejects_empty_values() -> None:
    with pytest.raises(ValueError):
        percentile([], 50)


def test_aggregate_latency_skips_missing_keys() -> None:
    turns = [
        _turn(0, {"asr_ms": 10, "reply_first_delta_ms": 30, "reply_delta_count": 8}),
        _turn(1, {"asr_ms": 20}),
    ]

    summary = aggregate_latency(turns)

    assert summary["asr_ms"].count == 2
    assert summary["asr_ms"].p50 == 15
    assert summary["reply_first_delta_ms"].count == 1
    assert summary["reply_first_delta_ms"].p90 == 30
    assert "reply_delta_count" not in summary


def test_build_run_record_fills_latency_summary() -> None:
    run = build_run_record(
        run_id="run-1",
        scenario_id="interview",
        mode="offline_fake",
        generated_at="2026-06-06T00:00:00+00:00",
        providers={"llm": "fake"},
        turns=[_turn(0, {"grammar_ms": 5})],
    )

    assert run.latency_summary["grammar_ms"].count == 1


def _turn(index: int, timings: dict[str, float]) -> TurnRecord:
    return TurnRecord(
        index=index,
        user_text="hello",
        asr_text="hello",
        expected_text="hello",
        audio_path=None,
        reply_text="hi",
        timings_ms=timings,
        wer=0.0,
    )
