from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class ASRResult:
    text: str
    provider: str
    confidence: float | None = None


class ASRProvider(Protocol):
    provider_name: str

    def partial(self, expected_text: str | None = None) -> str:
        """Return a partial transcript for perceived latency."""

    def transcribe(self, audio_bytes: bytes, expected_text: str | None = None) -> str:
        """Return final transcript text for one turn."""


class FakeASR:
    provider_name = "fake"
    default_transcript = "I have worked on backend systems for three years."

    def partial(self, expected_text: str | None = None) -> str:
        transcript = expected_text or self.default_transcript
        words = transcript.split()
        return " ".join(words[: min(4, len(words))])

    def transcribe(self, audio_bytes: bytes, expected_text: str | None = None) -> str:
        del audio_bytes
        return expected_text or self.default_transcript


class FasterWhisperASR:
    provider_name = "faster_whisper"

    def __init__(self, model_size: str | None = None) -> None:
        self.model_size = model_size or os.environ.get("ASR_MODEL_SIZE", "small")
        self._model = None

    def partial(self, expected_text: str | None = None) -> str:
        if expected_text:
            words = expected_text.split()
            return " ".join(words[: min(4, len(words))])
        return ""

    def transcribe(self, audio_bytes: bytes, expected_text: str | None = None) -> str:
        del expected_text
        model = self._load_model()
        audio_path = _write_temp_audio(audio_bytes)
        try:
            segments, _info = model.transcribe(str(audio_path), beam_size=1)
            return " ".join(segment.text.strip() for segment in segments if segment.text.strip())
        finally:
            audio_path.unlink(missing_ok=True)

    def _load_model(self):
        if self._model is not None:
            return self._model
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError(
                "faster-whisper is not installed. Install it before using ASR_PROVIDER=faster_whisper."
            ) from exc
        device = os.environ.get("ASR_DEVICE", "cpu")
        compute_type = os.environ.get("ASR_COMPUTE_TYPE", "int8")
        self._model = WhisperModel(self.model_size, device=device, compute_type=compute_type)
        return self._model


def create_asr_provider() -> ASRProvider:
    provider = os.environ.get("ASR_PROVIDER", "fake").strip().lower()
    if provider == "faster_whisper":
        return FasterWhisperASR()
    return FakeASR()


def _write_temp_audio(audio_bytes: bytes) -> Path:
    import tempfile

    handle = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
    with handle:
        handle.write(audio_bytes)
    return Path(handle.name)


asr_provider = create_asr_provider()
fake_asr = asr_provider
