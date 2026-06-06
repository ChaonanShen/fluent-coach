import base64
import sys
import types

import pytest

from backend.app.services.tts import KokoroTTSProvider


def test_kokoro_tts_provider_returns_wav_base64(monkeypatch, tmp_path) -> None:
    model_dir = tmp_path / "Kokoro-82M"
    model_dir.mkdir()
    (model_dir / "kokoro-v1_0.pth").write_bytes(b"model")
    voices_dir = model_dir / "voices"
    voices_dir.mkdir()
    (voices_dir / "af_heart.pt").write_bytes(b"voice")
    captured: dict[str, object] = {}

    class FakeKPipeline:
        def __init__(self, *, lang_code=None, model=None, repo_id=None, device=None):
            captured["lang_code"] = lang_code
            captured["model"] = model
            captured["repo_id"] = repo_id
            captured["device"] = device

        def __call__(self, text, *, voice):
            captured["text"] = text
            captured["voice"] = voice
            yield "gs", "ps", [0.0, 0.1, -0.1]

    fake_kokoro = types.ModuleType("kokoro")
    fake_kokoro.KPipeline = FakeKPipeline
    fake_soundfile = types.ModuleType("soundfile")

    def fake_write(buffer, waveform, sample_rate, *, format):
        del waveform
        buffer.write(f"{format}:{sample_rate}".encode("ascii"))

    fake_soundfile.write = fake_write
    monkeypatch.setitem(sys.modules, "kokoro", fake_kokoro)
    monkeypatch.setitem(sys.modules, "soundfile", fake_soundfile)
    monkeypatch.setenv("KOKORO_MODEL_DIR", str(model_dir))
    monkeypatch.setenv("KOKORO_VOICE", "af_heart")
    monkeypatch.setenv("KOKORO_LANG_CODE", "a")

    result = KokoroTTSProvider().synthesize("  I has three year experience.  ")

    assert result.provider == "kokoro"
    assert result.mime_type == "audio/wav"
    assert result.fallback_applied is False
    assert base64.b64decode(result.audio_base64 or "") == b"WAV:24000"
    assert captured["lang_code"] == "a"
    assert captured["model"] == str(model_dir / "kokoro-v1_0.pth")
    assert captured["text"] == "I has three year experience."
    assert captured["voice"] == "af_heart"


def test_kokoro_tts_provider_reports_missing_model_dir(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("KOKORO_MODEL_DIR", str(tmp_path / "missing"))

    with pytest.raises(RuntimeError, match="Kokoro model directory not found"):
        KokoroTTSProvider().synthesize("Hello")
