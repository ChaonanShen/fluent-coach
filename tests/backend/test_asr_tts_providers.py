import importlib.util

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services.asr import FakeASR, FasterWhisperASR, create_asr_provider
from backend.app.services.tts import BrowserTTSProvider, create_tts_provider


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
    assert result.fallback_applied is True


def test_tts_api_returns_browser_fallback() -> None:
    client = TestClient(app)

    response = client.post("/api/tts/synthesize", json={"text": "Hello"})

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == BrowserTTSProvider.provider_name
    assert body["audio_url"] is None
    assert body["fallback_applied"] is True
