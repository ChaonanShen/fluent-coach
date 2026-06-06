from scripts.run_conversation_bench import _dev_tts_provider_for


def test_dev_tts_provider_for_grammar_tts_fake_smoke(monkeypatch) -> None:
    monkeypatch.setenv("TTS_PROVIDER", "browser")

    provider = _dev_tts_provider_for(mode="grammar_tts", allow_fake_providers=True)

    assert provider is not None
    assert provider.provider_name == "fake_audio"
    result = provider.synthesize("I has three year experience.")
    assert result.mime_type == "audio/wav"
    assert result.audio_base64
    assert result.fallback_applied is False


def test_dev_tts_provider_keeps_real_tts(monkeypatch) -> None:
    monkeypatch.setenv("TTS_PROVIDER", "kokoro")

    provider = _dev_tts_provider_for(mode="grammar_tts", allow_fake_providers=True)

    assert provider is None
