from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from backend.app.testkit import run_store


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DASHBOARD_DIR = Path(__file__).resolve().parent / "dashboard"

dashboard_app = FastAPI(title="XEngineer Bench Dashboard")


@dashboard_app.get("/")
def index() -> FileResponse:
    return FileResponse(DASHBOARD_DIR / "index.html")


@dashboard_app.get("/api/runs")
def list_runs() -> list[dict[str, object]]:
    return run_store.list_runs()


@dashboard_app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> dict[str, object]:
    try:
        return run_store.load_run(run_id).model_dump(mode="json")
    except Exception as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc


@dashboard_app.get("/api/runs/{run_id}/turns/{turn_index}/audio")
def get_turn_audio(run_id: str, turn_index: int) -> FileResponse:
    try:
        run = run_store.load_run(run_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc
    if turn_index < 0 or turn_index >= len(run.turns):
        raise HTTPException(status_code=404, detail="Turn not found")
    audio_path = run.turns[turn_index].audio_path
    if not audio_path:
        raise HTTPException(status_code=404, detail="Audio not recorded")
    path = _resolve_audio_path(audio_path)
    if path is None or not path.is_file():
        raise HTTPException(status_code=404, detail="Audio not found")
    return FileResponse(path, media_type=_media_type(path))


def _resolve_audio_path(value: str) -> Path | None:
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    resolved = candidate.resolve()
    if any(_is_relative_to(resolved, root) for root in _allowed_audio_roots()):
        return resolved
    return None


def _allowed_audio_roots() -> list[Path]:
    roots = [
        PROJECT_ROOT / ".local/audio",
        _resolve_root(run_store.runs_dir()),
        PROJECT_ROOT / "reports",
    ]
    configured_audio_dir = os.environ.get("APP_AUDIO_DIR")
    if configured_audio_dir:
        roots.append(_resolve_root(Path(configured_audio_dir)))
    return [root.resolve() for root in roots]


def _resolve_root(path: Path) -> Path:
    expanded = path.expanduser()
    if expanded.is_absolute():
        return expanded
    return PROJECT_ROOT / expanded


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _media_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".wav":
        return "audio/wav"
    if suffix == ".mp3":
        return "audio/mpeg"
    if suffix == ".ogg":
        return "audio/ogg"
    if suffix == ".webm":
        return "audio/webm"
    if suffix == ".flac":
        return "audio/flac"
    return "application/octet-stream"
