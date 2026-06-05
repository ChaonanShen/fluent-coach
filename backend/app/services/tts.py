from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class TTSResult:
    provider: str
    text: str
    audio_url: str | None
    fallback_applied: bool


class TTSProvider(Protocol):
    provider_name: str

    def synthesize(self, text: str) -> TTSResult:
        """Return synthesized audio metadata or a browser fallback instruction."""


class BrowserTTSProvider:
    provider_name = "browser"

    def synthesize(self, text: str) -> TTSResult:
        return TTSResult(
            provider=self.provider_name,
            text=text,
            audio_url=None,
            fallback_applied=True,
        )


class DisabledCloudTTSProvider:
    provider_name = "cloud_disabled"

    def synthesize(self, text: str) -> TTSResult:
        return TTSResult(
            provider=self.provider_name,
            text=text,
            audio_url=None,
            fallback_applied=True,
        )


def create_tts_provider() -> TTSProvider:
    provider = os.environ.get("TTS_PROVIDER", "browser").strip().lower()
    if provider == "browser":
        return BrowserTTSProvider()
    return DisabledCloudTTSProvider()


tts_provider = create_tts_provider()
