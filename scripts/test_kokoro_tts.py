#!/usr/bin/env python3
"""Generate one local Kokoro TTS sample for manual smoke testing."""

from __future__ import annotations

import argparse
import base64
import time
from pathlib import Path

try:
    from scripts import _bootstrap  # noqa: F401
except ModuleNotFoundError:
    import _bootstrap  # noqa: F401
from backend.app.core.env import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Kokoro TTS smoke test.")
    parser.add_argument("--text", default="I has three year experience.", help="Text to synthesize.")
    parser.add_argument("--output", default="/tmp/kokoro-smoke.wav", help="Output wav path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    load_dotenv(force=True)
    from backend.app.services.tts import KokoroTTSProvider

    started = time.perf_counter()
    result = KokoroTTSProvider().synthesize(args.text)
    elapsed_ms = round((time.perf_counter() - started) * 1000.0, 1)
    if result.audio_base64 is None:
        raise RuntimeError("Kokoro TTS did not return audio.")
    output = _resolve_output(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    audio_bytes = base64.b64decode(result.audio_base64)
    output.write_bytes(audio_bytes)
    if len(audio_bytes) < 1024:
        raise RuntimeError(f"Kokoro TTS output is unexpectedly small: {len(audio_bytes)} bytes")
    print(f"provider={result.provider}")
    print(f"mime_type={result.mime_type}")
    print(f"tts_ms={elapsed_ms}")
    print(f"bytes={len(audio_bytes)}")
    print(f"wrote {output}")
    return 0


def _resolve_output(value: str) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


if __name__ == "__main__":
    raise SystemExit(main())
