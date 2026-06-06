from __future__ import annotations

import json
import os
from pathlib import Path

from backend.app.testkit.models import RunRecord


DEFAULT_RUNS_DIR = Path("reports/runs")


def runs_dir() -> Path:
    return Path(os.environ.get("BENCH_RUNS_DIR", str(DEFAULT_RUNS_DIR)))


def save_run(run: RunRecord) -> Path:
    directory = runs_dir()
    directory.mkdir(parents=True, exist_ok=True)
    path = _run_path(run.run_id)
    path.write_text(
        json.dumps(run.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def load_run(run_id: str) -> RunRecord:
    path = _run_path(run_id)
    payload = json.loads(path.read_text(encoding="utf-8"))
    return RunRecord.model_validate(payload)


def list_runs() -> list[dict[str, object]]:
    runs: list[dict[str, object]] = []
    for path in sorted(runs_dir().glob("*.json")):
        try:
            run = load_run(path.stem)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        runs.append(
            {
                "run_id": run.run_id,
                "scenario_id": run.scenario_id,
                "mode": run.mode,
                "generated_at": run.generated_at,
                "turn_count": len(run.turns),
            }
        )
    return sorted(runs, key=lambda item: str(item["generated_at"]), reverse=True)


def _run_path(run_id: str) -> Path:
    if not run_id or Path(run_id).name != run_id or run_id in {".", ".."}:
        raise ValueError(f"Invalid run_id: {run_id}")
    return runs_dir() / f"{run_id}.json"
