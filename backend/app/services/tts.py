from __future__ import annotations

import base64
import inspect
import os
from io import BytesIO
from dataclasses import dataclass
from pathlib import Path
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


class KokoroTTSProvider:
    provider_name = "kokoro"

    def __init__(self) -> None:
        self.model_dir = Path(os.environ.get("KOKORO_MODEL_DIR", "models/tts/Kokoro-82M"))
        self.model_path = Path(os.environ.get("KOKORO_MODEL_PATH", str(self.model_dir / "kokoro-v1_0.pth")))
        self.voice = os.environ.get("KOKORO_VOICE", "af_heart")
        self.lang_code = os.environ.get("KOKORO_LANG_CODE", "a")
        self.sample_rate = int(os.environ.get("KOKORO_SAMPLE_RATE", "24000") or 24000)
        self.device = os.environ.get("KOKORO_DEVICE", "").strip() or None
        self._pipeline_instance = None

    def synthesize(self, text: str) -> TTSResult:
        normalized = " ".join(text.split())
        if not normalized:
            raise RuntimeError("Kokoro TTS requires non-empty text.")
        audio_bytes = self._synthesize_wav_bytes(normalized)
        return TTSResult(
            provider=self.provider_name,
            text=text,
            audio_url=None,
            audio_base64=base64.b64encode(audio_bytes).decode("ascii"),
            mime_type="audio/wav",
            fallback_applied=False,
        )

    def _synthesize_wav_bytes(self, text: str) -> bytes:
        pipeline = self._get_pipeline()
        try:
            import numpy as np
            import soundfile as sf
        except ImportError as exc:
            raise RuntimeError(
                "Kokoro TTS requires optional dependencies. Install with: python3 -m pip install -e '.[tts]'"
            ) from exc

        chunks = []
        for item in pipeline(text, voice=self._voice_value()):
            audio = getattr(item, "audio", None)
            if audio is None:
                audio = item[-1] if isinstance(item, tuple) else item
            chunks.append(_audio_to_numpy(audio, np))
        if not chunks:
            raise RuntimeError("Kokoro TTS returned no audio chunks.")
        waveform = chunks[0] if len(chunks) == 1 else np.concatenate(chunks)
        buffer = BytesIO()
        sf.write(buffer, waveform, self.sample_rate, format="WAV")
        return buffer.getvalue()

    def _get_pipeline(self):
        if self._pipeline_instance is not None:
            return self._pipeline_instance
        if not self.model_dir.exists():
            raise RuntimeError(f"Kokoro model directory not found: {self.model_dir}")
        try:
            from kokoro import KModel, KPipeline
        except ImportError as exc:
            raise RuntimeError(
                "Kokoro TTS requires the kokoro package. Install with: python3 -m pip install -e '.[tts]'"
            ) from exc
        kwargs = self._pipeline_kwargs(KPipeline, KModel)
        self._pipeline_instance = KPipeline(**kwargs)
        return self._pipeline_instance

    def _pipeline_kwargs(self, pipeline_cls: object, model_cls: object | None = None) -> dict[str, object]:
        signature = inspect.signature(pipeline_cls)
        kwargs: dict[str, object] = {"lang_code": self.lang_code}
        parameters = signature.parameters
        if "model" in parameters and self.model_path.exists():
            config_path = self.model_dir / "config.json"
            if model_cls is not None and config_path.exists():
                kwargs["model"] = model_cls(
                    config=str(config_path),
                    model=str(self.model_path),
                )
            else:
                kwargs["model"] = str(self.model_path)
        if "device" in parameters and self.device is not None:
            kwargs["device"] = self.device
        return kwargs

    def _voice_value(self) -> str:
        voice_path = self.model_dir / "voices" / f"{self.voice}.pt"
        if voice_path.exists() or os.environ.get("KOKORO_VOICE_AS_PATH", "").strip().lower() in {"1", "true", "yes", "on"}:
            return str(voice_path)
        return self.voice


def create_tts_provider() -> TTSProvider:
    provider = os.environ.get("TTS_PROVIDER", "browser").strip().lower()
    if provider == "browser":
        return BrowserTTSProvider()
    if provider == "openai_compatible":
        return OpenAICompatibleTTSProvider()
    if provider == "kokoro":
        return KokoroTTSProvider()
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


def _audio_to_numpy(audio: object, np):
    if hasattr(audio, "detach"):
        audio = audio.detach().cpu().numpy()
    return np.asarray(audio, dtype="float32")
