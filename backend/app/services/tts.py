from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from typing import Protocol

import httpx


@dataclass(frozen=True)
class TTSResult:
    provider: str
    text: str
    audio_url: str | None
    audio_base64: str | None
    mime_type: str | None
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
            audio_base64=None,
            mime_type=None,
            fallback_applied=True,
        )


class DisabledCloudTTSProvider:
    provider_name = "cloud_disabled"

    def synthesize(self, text: str) -> TTSResult:
        return TTSResult(
            provider=self.provider_name,
            text=text,
            audio_url=None,
            audio_base64=None,
            mime_type=None,
            fallback_applied=True,
        )


class OpenAICompatibleTTSProvider:
    provider_name = "openai_compatible"

    def __init__(self, http_client: httpx.Client | None = None) -> None:
        self.base_url = os.environ.get("TTS_BASE_URL") or os.environ.get("LLM_BASE_URL", "")
        self.api_key = os.environ.get("TTS_API_KEY") or os.environ.get("LLM_API_KEY", "")
        self.model = os.environ.get("TTS_MODEL", "tts-1")
        self.voice = os.environ.get("TTS_VOICE", "alloy")
        self.response_format = os.environ.get("TTS_RESPONSE_FORMAT", "mp3")
        timeout = float(os.environ.get("TTS_TIMEOUT_SECONDS", "30") or 30)
        self._client = http_client or httpx.Client(timeout=timeout)

    def synthesize(self, text: str) -> TTSResult:
        if not self.base_url.strip() or not self.api_key.strip():
            return DisabledCloudTTSProvider().synthesize(text)
        response = self._client.post(
            f"{self.base_url.rstrip('/')}/audio/speech",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "voice": self.voice,
                "input": text,
                "response_format": self.response_format,
            },
        )
        response.raise_for_status()
        return TTSResult(
            provider=self.provider_name,
            text=text,
            audio_url=None,
            audio_base64=base64.b64encode(response.content).decode("ascii"),
            mime_type=_mime_type_for_format(self.response_format),
            fallback_applied=False,
        )


def create_tts_provider() -> TTSProvider:
    provider = os.environ.get("TTS_PROVIDER", "browser").strip().lower()
    if provider == "browser":
        return BrowserTTSProvider()
    if provider == "openai_compatible":
        return OpenAICompatibleTTSProvider()
    return DisabledCloudTTSProvider()


tts_provider = create_tts_provider()


def _mime_type_for_format(response_format: str) -> str:
    normalized = response_format.strip().lower()
    if normalized == "wav":
        return "audio/wav"
    if normalized == "opus":
        return "audio/ogg"
    if normalized == "aac":
        return "audio/aac"
    if normalized == "flac":
        return "audio/flac"
    return "audio/mpeg"
