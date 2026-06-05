#!/usr/bin/env python3
"""Run a local ASR provider smoke test with fixture audio."""

from __future__ import annotations

import argparse
import os

from backend.app.core.env import load_dotenv
from backend.app.core.fixtures import load_generated_manifest, resolve_fixture_audio
from backend.app.services.asr import FakeASR, FasterWhisperASR, create_asr_provider


def main() -> int:
    args = parse_args()
    load_dotenv(force=True)
    if args.provider:
        os.environ["ASR_PROVIDER"] = args.provider
    if args.model_size:
        os.environ["ASR_MODEL_SIZE"] = args.model_size

    item = load_generated_manifest(args.dataset)["items"][args.index]
    audio_path = resolve_fixture_audio(item["audio_file"])
    expected = item["transcript"]
    provider = create_asr_provider()

    print(f"provider={provider.provider_name}")
    print(f"audio={audio_path}")
    print(f"expected={expected}")

    if isinstance(provider, FasterWhisperASR):
        transcript = provider.transcribe_file(audio_path)
    else:
        transcript = provider.transcribe(audio_path.read_bytes(), expected_text=expected)

    print(f"transcript={transcript}")
    if isinstance(provider, FakeASR):
        print("Fake ASR smoke passed. Set ASR_PROVIDER=faster_whisper for real ASR.")
    else:
        print("ASR smoke passed.")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="librispeech", choices=["librispeech", "l2_arctic"])
    parser.add_argument("--index", type=int, default=0)
    parser.add_argument("--provider", choices=["fake", "faster_whisper"], default=None)
    parser.add_argument("--model-size", default=None)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
