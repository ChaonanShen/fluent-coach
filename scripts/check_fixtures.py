#!/usr/bin/env python3
"""Ensure generated fixture data exists before tests or dev servers run."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

REQUIRED_PATHS = [
    Path("fixtures/generated/dataset_subset_summary.json"),
    Path("fixtures/generated/librispeech_subset.json"),
    Path("fixtures/generated/speechocean762_subset.json"),
    Path("fixtures/generated/l2_arctic_subset.json"),
    Path("fixtures/generated/jfleg_subset.json"),
    Path("fixtures/audio/public"),
]


def main() -> int:
    missing = [path for path in REQUIRED_PATHS if not (PROJECT_ROOT / path).exists()]
    if not missing:
        print("fixtures ready")
        return 0

    bundle = PROJECT_ROOT / "fixture-subset.zip"
    if bundle.exists():
        print("fixtures missing; extracting fixture-subset.zip")
        return subprocess.call([sys.executable, "scripts/extract_fixtures.py"], cwd=PROJECT_ROOT)

    print("fixtures missing:")
    for path in missing:
        print(f"- {path}")
    print(
        "Expected fixture-subset.zip at the project root. "
        "Restore it or run scripts/prepare_fixtures.py."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
