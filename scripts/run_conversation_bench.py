#!/usr/bin/env python3
"""Run a backend-only multi-turn WebSocket conversation bench."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
AUDIO_SUFFIXES = {".wav", ".mp3", ".ogg", ".webm", ".flac"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run conversation WebSocket bench.")
    parser.add_argument("--scenario", default="interview", help="Scenario id, default: interview")
    parser.add_argument("--turns", type=int, default=10, help="Number of turns, default: 10")
    parser.add_argument(
        "--mode",
        choices=["offline_fake", "real", "real_audio", "grammar_tts"],
        default="offline_fake",
        help="Bench mode, default: offline_fake",
    )
    parser.add_argument(
        "--transcript-source",
        choices=["scripted"],
        default="scripted",
        help="Offline transcript source, default: scripted",
    )
    parser.add_argument("--real", action="store_true", help="Use configured real providers.")
    parser.add_argument(
        "--virtual-user",
        choices=["template", "llm"],
        default="template",
        help="Virtual user source for grammar_tts, default: template.",
    )
    parser.add_argument(
        "--allow-fake-providers",
        action="store_true",
        help="Allow fake ASR/TTS providers in grammar_tts for development tests.",
    )
    parser.add_argument("--audio-file", action="append", default=[], help="Real-mode audio file; repeatable.")
    parser.add_argument("--audio-dir", help="Real-mode directory of audio files.")
    parser.add_argument("--output-dir", default="reports", help="Output directory, default: reports")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = _resolve_output_dir(args.output_dir)
    os.environ["BENCH_RUNS_DIR"] = str(output_dir / "runs")
    audio_paths = _resolve_audio_paths(args)
    mode = _selected_mode(args)

    if mode == "real":
        if not audio_paths:
            raise SystemExit("--real requires --audio-file or --audio-dir with at least one audio file")
        from backend.app.core.env import load_dotenv

        load_dotenv(force=True)
    elif mode == "grammar_tts":
        from backend.app.core.env import load_dotenv

        load_dotenv(force=True)
    else:
        os.environ["ASR_PROVIDER"] = "fake"
        os.environ["LLM_PROVIDER"] = "fake"
        os.environ["PRON_PROVIDER"] = "mock"

    from backend.app.core.env import provider_status
    from backend.app.testkit.report import build_run_record, render_markdown
    from backend.app.testkit.run_store import save_run
    from backend.app.testkit.ws_driver import run_ws_conversation

    generated_at = datetime.now(timezone.utc)
    run_id = f"{generated_at.strftime('%Y%m%dT%H%M%SZ')}-{args.scenario}-{mode}"
    turns = run_ws_conversation(
        scenario_id=args.scenario,
        turns=args.turns,
        transcript_source=args.transcript_source,
        mode=mode,
        audio_paths=audio_paths,
        virtual_user_source=args.virtual_user,
        allow_fake_providers=args.allow_fake_providers,
    )
    status = provider_status()
    providers = {
        "llm": _string_or_none(status.get("llm_provider")),
        "asr": _string_or_none(status.get("asr_provider")),
        "pronunciation": _string_or_none(status.get("pronunciation_provider")),
        "tts": _string_or_none(status.get("tts_provider")),
    }
    run = build_run_record(
        run_id=run_id,
        scenario_id=args.scenario,
        mode=mode,
        generated_at=generated_at.isoformat(),
        providers=providers,
        turns=turns,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    run_path = save_run(run)
    latest_json = output_dir / "bench-latest.json"
    latest_md = output_dir / "bench-latest.md"
    latest_json.write_text(
        json.dumps(run.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    latest_md.write_text(render_markdown(run), encoding="utf-8")

    print(f"wrote {run_path}")
    print(f"wrote {latest_json}")
    print(f"wrote {latest_md}")
    _print_latency_summary(run.latency_summary)
    return 0


def _resolve_output_dir(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def _selected_mode(args: argparse.Namespace) -> str:
    if args.real:
        return "real"
    if args.mode == "real_audio":
        return "real"
    return args.mode


def _resolve_audio_paths(args: argparse.Namespace) -> list[Path]:
    paths = [_resolve_project_path(value) for value in args.audio_file]
    if args.audio_dir:
        audio_dir = _resolve_project_path(args.audio_dir)
        paths.extend(
            path
            for path in sorted(audio_dir.iterdir())
            if path.is_file() and path.suffix.lower() in AUDIO_SUFFIXES
        )
    missing = [str(path) for path in paths if not path.exists()]
    if missing:
        raise SystemExit(f"audio file not found: {missing[0]}")
    return paths


def _resolve_project_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def _string_or_none(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _print_latency_summary(summary: object) -> None:
    if not isinstance(summary, dict) or not summary:
        return
    for key in sorted(summary):
        stat = summary[key]
        print(f"{key}: p50={stat.p50:.3f}ms p90={stat.p90:.3f}ms count={stat.count}")


if __name__ == "__main__":
    raise SystemExit(main())
