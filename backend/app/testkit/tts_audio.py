from __future__ import annotations

import base64
import time
from typing import Protocol

from backend.app.services.tts import TTSResult


class SynthesizingTTSProvider(Protocol):
    provider_name: str

    def synthesize(self, text: str) -> TTSResult:
        """Return synthesized audio."""


def synthesize_turn_audio(
    text: str,
    provider: SynthesizingTTSProvider,
) -> tuple[bytes, str, dict[str, object], dict[str, float]]:
    started = time.perf_counter()
    result = provider.synthesize(text)
    tts_ms = round((time.perf_counter() - started) * 1000.0, 1)
    if result.fallback_applied or not result.audio_base64:
        raise RuntimeError(f"TTS provider {result.provider} did not return audio bytes")
    try:
        audio_bytes = base64.b64decode(result.audio_base64)
    except ValueError as exc:
        raise RuntimeError(f"TTS provider {result.provider} returned invalid base64 audio") from exc
    if not audio_bytes:
        raise RuntimeError(f"TTS provider {result.provider} returned empty audio")
    mime_type = result.mime_type or "audio/wav"
    return (
        audio_bytes,
        mime_type,
        {
            "provider": result.provider,
            "mime_type": mime_type,
            "voice": getattr(provider, "voice", None),
            "text": result.text,
        },
        {"tts_ms": tts_ms},
    )
