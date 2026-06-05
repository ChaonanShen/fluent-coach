#!/usr/bin/env python3
"""Extract the tracked fixture bundle back into the working tree.

`fixture-subset.zip` is committed to git so anyone can run the tests without
downloading the multi-gigabyte raw datasets. This script unpacks it into the
project root, restoring:

  fixtures/generated/...      (JSON manifests)
  fixtures/audio/public/...   (selected subset audio)

It is the inverse of scripts/prepare_fixtures.py. Idempotent: re-running just
overwrites the extracted files.
"""

from __future__ import annotations

import argparse
import zipfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Unpack fixture-subset.zip into fixtures/ at the project root."
    )
    parser.add_argument(
        "--bundle-zip",
        default="fixture-subset.zip",
        help="Bundle to extract (default: fixture-subset.zip).",
    )
    parser.add_argument(
        "--dest",
        default=".",
        help="Destination root, relative to the project root (default: project root).",
    )
    return parser.parse_args()


def resolve_project_path(raw: str) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def safe_member_path(target_dir: Path, member_name: str) -> Path:
    destination = (target_dir / member_name).resolve()
    target = target_dir.resolve()
    if destination != target and target not in destination.parents:
        raise RuntimeError(f"Unsafe archive member path: {member_name}")
    return destination


def main() -> int:
    args = parse_args()
    bundle = resolve_project_path(args.bundle_zip)
    dest = resolve_project_path(args.dest)

    if not bundle.exists():
        print(f"error: bundle not found: {bundle}")
        print("Run scripts/prepare_fixtures.py first, or check the path.")
        return 1

    dest.mkdir(parents=True, exist_ok=True)
    count = 0
    with zipfile.ZipFile(bundle) as zf:
        for member in zf.namelist():
            safe_member_path(dest, member)
        for member in zf.infolist():
            if member.is_dir():
                continue
            zf.extract(member, dest)
            count += 1

    print(f"extracted {count} files from {bundle.name} -> {dest}")
    print("ready: fixtures/generated/ and fixtures/audio/public/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
