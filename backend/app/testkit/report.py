from __future__ import annotations

import math
from statistics import mean

from backend.app.testkit.models import LatencyStat, RunRecord, TurnRecord


def percentile(values: list[float], p: float) -> float:
    if not values:
        raise ValueError("percentile requires at least one value")
    if p < 0 or p > 100:
        raise ValueError("percentile p must be between 0 and 100")
    ordered = sorted(values)
    if len(ordered) == 1:
        return round(ordered[0], 3)
    rank = (len(ordered) - 1) * (p / 100.0)
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return round(ordered[int(rank)], 3)
    weight = rank - lower
    return round(ordered[lower] + (ordered[upper] - ordered[lower]) * weight, 3)


def aggregate_latency(turns: list[TurnRecord]) -> dict[str, LatencyStat]:
    values_by_key: dict[str, list[float]] = {}
    for turn in turns:
        for key, value in turn.timings_ms.items():
            if not key.endswith("_ms"):
                continue
            if isinstance(value, bool):
                continue
            values_by_key.setdefault(key, []).append(float(value))

    return {
        key: LatencyStat(
            p50=percentile(values, 50),
            p90=percentile(values, 90),
            p95=percentile(values, 95),
            max=round(max(values), 3),
            mean=round(mean(values), 3),
            count=len(values),
        )
        for key, values in sorted(values_by_key.items())
        if values
    }


def build_run_record(
    *,
    run_id: str,
    scenario_id: str,
    mode: str,
    generated_at: str,
    providers: dict[str, str | None],
    turns: list[TurnRecord],
) -> RunRecord:
    return RunRecord(
        run_id=run_id,
        scenario_id=scenario_id,
        mode=mode,
        generated_at=generated_at,
        providers=providers,
        turns=turns,
        latency_summary=aggregate_latency(turns),
    )


def render_markdown(run: RunRecord) -> str:
    lines = [
        "# Conversation Bench Report",
        "",
        f"Run ID: `{run.run_id}`",
        f"Generated at: `{run.generated_at}`",
        f"Scenario: `{run.scenario_id}`",
        f"Mode: `{run.mode}`",
        f"Turns: `{len(run.turns)}`",
        "",
        "## Providers",
        "",
    ]
    if run.providers:
        lines.extend(f"- {name}: `{value or 'none'}`" for name, value in sorted(run.providers.items()))
    else:
        lines.append("- none")

    lines.extend(["", "## Latency", ""])
    if run.latency_summary:
        lines.append("| Segment | p50 | p90 | p95 | max | mean | count |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|")
        for segment, stat in sorted(run.latency_summary.items()):
            lines.append(
                f"| `{segment}` | {stat.p50:.3f} | {stat.p90:.3f} | {stat.p95:.3f} | "
                f"{stat.max:.3f} | {stat.mean:.3f} | {stat.count} |"
            )
    else:
        lines.append("No latency samples were recorded.")

    grammar_summary = grammar_metric_summary(run.turns)
    if grammar_summary:
        lines.extend(["", "## Grammar Metrics", ""])
        lines.append(f"- Average expected error recall: {grammar_summary['average_expected_error_recall']:.4f}")
        lines.append(f"- Corrected text match rate: {grammar_summary['corrected_text_match_rate']:.4f}")
        lines.append(f"- Average WER against injected text: {grammar_summary['average_wer']:.4f}")

    lines.extend(["", "## Turns", ""])
    if run.turns:
        lines.append("| # | WER | ASR text | Reply |")
        lines.append("|---:|---:|---|---|")
        for turn in run.turns:
            wer = "" if turn.wer is None else f"{turn.wer:.4f}"
            lines.append(
                f"| {turn.index} | {wer} | {_md_cell(turn.asr_text)} | {_md_cell(turn.reply_text)} |"
            )
    else:
        lines.append("No turns were recorded.")
    lines.append("")
    return "\n".join(lines)


def grammar_metric_summary(turns: list[TurnRecord]) -> dict[str, float]:
    metric_turns = [turn for turn in turns if turn.grammar_metrics]
    if not metric_turns:
        return {}
    recalls = [
        float(turn.grammar_metrics.get("expected_error_recall", 0.0))
        for turn in metric_turns
        if not isinstance(turn.grammar_metrics.get("expected_error_recall"), bool)
    ]
    corrected_matches = [
        1.0 if turn.grammar_metrics.get("corrected_text_match") is True else 0.0
        for turn in metric_turns
    ]
    wers = [turn.wer for turn in metric_turns if turn.wer is not None]
    return {
        "average_expected_error_recall": round(mean(recalls), 4) if recalls else 0.0,
        "corrected_text_match_rate": round(mean(corrected_matches), 4) if corrected_matches else 0.0,
        "average_wer": round(mean(wers), 4) if wers else 0.0,
    }


def _md_cell(value: str) -> str:
    return " ".join(value.split()).replace("|", "\\|")
