import base64

import pytest

from backend.app.services.tts import TTSResult
from backend.app.testkit.tts_audio import synthesize_turn_audio


class FakeAudioTTS:
    provider_name = "fake_audio"
    voice = "test_voice"

    def synthesize(self, text: str) -> TTSResult:
        return TTSResult(
            provider=self.provider_name,
            text=text,
            audio_url=None,
            audio_base64=base64.b64encode(b"wav-bytes").decode("ascii"),
            mime_type="audio/wav",
            fallback_applied=False,
        )


class FallbackTTS:
    provider_name = "fallback"

    def synthesize(self, text: str) -> TTSResult:
        return TTSResult(
            provider=self.provider_name,
            text=text,
            audio_url=None,
            audio_base64=None,
            mime_type=None,
            fallback_applied=True,
        )


def test_synthesize_turn_audio_returns_bytes_meta_and_timing() -> None:
    audio_bytes, mime_type, meta, timings = synthesize_turn_audio("Hello", FakeAudioTTS())

    assert audio_bytes == b"wav-bytes"
    assert mime_type == "audio/wav"
    assert meta["provider"] == "fake_audio"
    assert meta["voice"] == "test_voice"
    assert meta["text"] == "Hello"
    assert timings["tts_ms"] >= 0


def test_synthesize_turn_audio_rejects_fallback_provider() -> None:
    with pytest.raises(RuntimeError, match="did not return audio bytes"):
        synthesize_turn_audio("Hello", FallbackTTS())
