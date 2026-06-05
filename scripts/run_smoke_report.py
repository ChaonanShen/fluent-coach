#!/usr/bin/env python3
"""Generate smoke reports.

The default fixture mode never calls external services. Real mode must be
requested explicitly and records failures in the report instead of failing CI.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.app.core.env import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run smoke report.")
    parser.add_argument("--output-dir", default="reports", help="Output directory, default: reports")
    parser.add_argument(
        "--mode",
        choices=["fixture", "real"],
        default="fixture",
        help="fixture uses fake/mock providers; real uses configured providers explicitly.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.mode == "real":
        load_dotenv()
    from backend.app.eval.smoke import render_smoke_markdown, run_fixture_smoke_report, run_real_smoke_report

    output_dir = PROJECT_ROOT / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    report = run_real_smoke_report() if args.mode == "real" else run_fixture_smoke_report()
    prefix = "smoke-real-latest" if args.mode == "real" else "smoke-latest"
    (output_dir / f"{prefix}.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / f"{prefix}.md").write_text(render_smoke_markdown(report), encoding="utf-8")
    print(f"wrote {output_dir / f'{prefix}.json'}")
    print(f"wrote {output_dir / f'{prefix}.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
