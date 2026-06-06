import importlib.util

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services.asr import FakeASR, FasterWhisperASR, create_asr_provider
from backend.app.services.tts import (
    BrowserTTSProvider,
    KokoroTTSProvider,
    OpenAICompatibleTTSProvider,
    create_tts_provider,
)


def test_fake_asr_returns_expected_partial_and_final() -> None:
    provider = FakeASR()

    assert provider.partial("one two three four five") == "one two three four"
    assert provider.transcribe(b"audio", "hello world") == "hello world"


def test_asr_provider_defaults_to_fake(monkeypatch) -> None:
    monkeypatch.delenv("ASR_PROVIDER", raising=False)

    assert isinstance(create_asr_provider(), FakeASR)


def test_faster_whisper_provider_reports_missing_dependency() -> None:
    if importlib.util.find_spec("faster_whisper") is not None:
        pytest.skip("covered by integration test when faster-whisper is installed")
    provider = FasterWhisperASR(model_size="tiny")

    try:
        provider._load_model()
    except RuntimeError as exc:
        assert "faster-whisper" in str(exc)
    else:
        assert provider.provider_name == "faster_whisper"


def test_tts_provider_defaults_to_browser(monkeypatch) -> None:
    monkeypatch.delenv("TTS_PROVIDER", raising=False)

    result = create_tts_provider().synthesize("Hello")

    assert result.provider == "browser"
    assert result.audio_url is None
    assert result.audio_base64 is None
    assert result.fallback_applied is True


def test_openai_compatible_tts_provider_returns_base64_audio(monkeypatch) -> None:
    monkeypatch.setenv("TTS_BASE_URL", "https://tts.example.test/v1")
    monkeypatch.setenv("TTS_API_KEY", "test-key")
    monkeypatch.setenv("TTS_MODEL", "tts-test")
    monkeypatch.setenv("TTS_VOICE", "voice-test")
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers["Authorization"]
        captured["payload"] = request.read()
        return httpx.Response(200, content=b"audio-bytes")

    provider = OpenAICompatibleTTSProvider(http_client=httpx.Client(transport=httpx.MockTransport(handler)))

    result = provider.synthesize("Hello")

    assert result.provider == "openai_compatible"
    assert result.audio_base64 == "YXVkaW8tYnl0ZXM="
    assert result.mime_type == "audio/mpeg"
    assert result.fallback_applied is False
    assert captured["url"] == "https://tts.example.test/v1/audio/speech"
    assert captured["auth"] == "Bearer test-key"
    assert b'"voice":"voice-test"' in captured["payload"]


def test_tts_factory_builds_openai_compatible_provider(monkeypatch) -> None:
    monkeypatch.setenv("TTS_PROVIDER", "openai_compatible")

    assert isinstance(create_tts_provider(), OpenAICompatibleTTSProvider)


def test_tts_factory_builds_kokoro_provider(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("TTS_PROVIDER", "kokoro")
    monkeypatch.setenv("KOKORO_MODEL_DIR", str(tmp_path))

    provider = create_tts_provider()

    assert isinstance(provider, KokoroTTSProvider)
    assert provider.provider_name == "kokoro"


def test_tts_api_returns_browser_fallback() -> None:
    client = TestClient(app)

    response = client.post("/api/tts/synthesize", json={"text": "Hello"})

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == BrowserTTSProvider.provider_name
    assert body["audio_url"] is None
    assert body["audio_base64"] is None
    assert body["mime_type"] is None
    assert body["fallback_applied"] is True
