from __future__ import annotations

import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4


DEFAULT_AUDIO_ROOT = Path(".local/audio")


@dataclass(frozen=True)
class StoredAudio:
    raw_path: Path
    wav_path: Path | None
    conversion_error: str | None = None
    raw_write_ms: float = 0.0
    transcode_ms: float = 0.0
    total_ms: float = 0.0

    @property
    def preferred_path(self) -> Path:
        return self.wav_path or self.raw_path


def save_turn_audio(
    *,
    session_id: str,
    audio_bytes: bytes,
    mime_type: str | None = None,
) -> StoredAudio:
    started = time.perf_counter()
    audio_root = Path(os.environ.get("APP_AUDIO_DIR", str(DEFAULT_AUDIO_ROOT)))
    session_dir = audio_root / _safe_name(session_id)
    session_dir.mkdir(parents=True, exist_ok=True)

    suffix = _suffix_for_mime_type(mime_type)
    raw_path = session_dir / f"{uuid4()}.{suffix}"
    write_started = time.perf_counter()
    raw_path.write_bytes(audio_bytes)
    raw_write_ms = _elapsed_ms(write_started)

    wav_path, conversion_error, transcode_ms = _convert_to_wav(raw_path)
    return StoredAudio(
        raw_path=raw_path,
        wav_path=wav_path,
        conversion_error=conversion_error,
        raw_write_ms=raw_write_ms,
        transcode_ms=transcode_ms,
        total_ms=_elapsed_ms(started),
    )


def _convert_to_wav(audio_path: Path) -> tuple[Path | None, str | None, float]:
    started = time.perf_counter()
    if audio_path.suffix.lower() == ".wav":
        return audio_path, None, _elapsed_ms(started)
    if shutil.which("ffmpeg") is None:
        return None, "ffmpeg_missing", _elapsed_ms(started)

    wav_path = audio_path.with_suffix(".wav")
    completed = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(audio_path),
            "-ac",
            "1",
            "-ar",
            "16000",
            str(wav_path),
        ],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if completed.returncode != 0 or not wav_path.exists():
        wav_path.unlink(missing_ok=True)
        return None, "transcode_failed", _elapsed_ms(started)
    return wav_path, None, _elapsed_ms(started)


def _suffix_for_mime_type(mime_type: str | None) -> str:
    normalized = (mime_type or "").split(";", 1)[0].strip().lower()
    if normalized in {"audio/wav", "audio/wave", "audio/x-wav"}:
        return "wav"
    if normalized in {"audio/mpeg", "audio/mp3"}:
        return "mp3"
    if normalized in {"audio/ogg", "audio/opus"}:
        return "ogg"
    if normalized in {"audio/webm", "video/webm"}:
        return "webm"
    return "webm"


def _safe_name(value: str) -> str:
    safe = "".join(char for char in value if char.isalnum() or char in {"-", "_"})
    return safe or "unknown"


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000.0, 1)
