#!/usr/bin/env python3
"""Generate a fixture-backed smoke report without calling external services."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.app.eval.smoke import render_smoke_markdown, run_fixture_smoke_report


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run fixture-backed smoke report.")
    parser.add_argument("--output-dir", default="reports", help="Output directory, default: reports")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = PROJECT_ROOT / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    report = run_fixture_smoke_report()
    (output_dir / "smoke-latest.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "smoke-latest.md").write_text(render_smoke_markdown(report), encoding="utf-8")
    print(f"wrote {output_dir / 'smoke-latest.json'}")
    print(f"wrote {output_dir / 'smoke-latest.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
