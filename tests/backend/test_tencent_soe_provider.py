from urllib.parse import parse_qs, urlsplit

from backend.app.services.pronunciation import (
    EVAL_MODE_SENTENCE,
    EVAL_MODE_WORD,
    TencentSOEProvider,
    build_tencent_signed_url,
    eval_mode_for_mode,
    infer_voice_format,
    normalize_tencent_score,
    tencent_signed_url_diagnostics,
)


def test_build_tencent_signed_url_uses_expected_path_and_query(monkeypatch) -> None:
    monkeypatch.setenv("TENCENT_APP_ID", "123456")
    monkeypatch.setenv("TENCENT_SECRET_ID", "secret-id")
    monkeypatch.setenv("TENCENT_SECRET_KEY", "secret-key")
    monkeypatch.setenv("TENCENT_SOE_WS_URL", "wss://soe.cloud.tencent.com/soe/api")

    url = build_tencent_signed_url(
        ref_text="HELLO WORLD",
        voice_format=1,
        timestamp=1000,
        nonce=42,
        voice_id="voice-1",
    )

    parsed = urlsplit(url)
    query = parse_qs(parsed.query)
    assert parsed.scheme == "wss"
    assert parsed.netloc == "soe.cloud.tencent.com"
    assert parsed.path == "/soe/api/123456"
    assert query["ref_text"] == ["HELLO WORLD"]
    assert query["voice_format"] == ["1"]
    assert query["secretid"] == ["secret-id"]
    assert query["timestamp"] == ["1000"]
    assert query["nonce"] == ["42"]
    assert query["rec_mode"] == ["1"]
    assert "signature" in query


def test_build_tencent_signed_url_allows_rec_mode_override(monkeypatch) -> None:
    monkeypatch.setenv("TENCENT_APP_ID", "123456")
    monkeypatch.setenv("TENCENT_SECRET_ID", "secret-id")
    monkeypatch.setenv("TENCENT_SECRET_KEY", "secret-key")
    monkeypatch.setenv("TENCENT_SOE_REC_MODE", "0")

    url = build_tencent_signed_url(
        ref_text="HELLO WORLD",
        voice_format=1,
        timestamp=1000,
        nonce=42,
        voice_id="voice-1",
    )

    assert parse_qs(urlsplit(url).query)["rec_mode"] == ["0"]


def test_tencent_signed_url_diagnostics_redacts_sensitive_values(monkeypatch) -> None:
    monkeypatch.setenv("TENCENT_APP_ID", "123456")
    monkeypatch.setenv("TENCENT_SECRET_ID", "secret-id")
    monkeypatch.setenv("TENCENT_SECRET_KEY", "secret-key")

    url = build_tencent_signed_url(
        ref_text="HELLO WORLD",
        voice_format=1,
        timestamp=1000,
        nonce=42,
        voice_id="voice-1",
    )

    diagnostics = tencent_signed_url_diagnostics(url)

    assert diagnostics["host"] == "soe.cloud.tencent.com"
    assert diagnostics["path_shape"] == "/soe/api/<appid>"
    assert diagnostics["has_signature"] is True
    assert diagnostics["signature_chars"] > 0
    assert diagnostics["has_secretid"] is True
    assert diagnostics["ref_text_chars"] == len("HELLO WORLD")
    assert "123456" not in str(diagnostics)
    assert "secret-id" not in str(diagnostics)


def test_tencent_result_maps_to_internal_pronunciation_model() -> None:
    result = {
        "SuggestedScore": 64.8,
        "PronAccuracy": 64.8,
        "PronFluency": 0.92,
        "PronCompletion": 1,
        "Words": [
            {
                "Word": "theme",
                "PronAccuracy": 31.07,
                "PhoneInfos": [
                    {"Phone": "TH", "PronAccuracy": 20},
                    {"Phone": "IY", "PronAccuracy": 40},
                ],
            },
            {"Word": "park", "PronAccuracy": 84.29},
        ],
    }

    assessment = TencentSOEProvider().map_result(
        result=result,
        reference_text="THEN HE WENT TO THEME PARK",
        audio_file="audio/public/speechocean762_subset/speechocean_000010113.wav",
    )

    assert assessment.provider == "tencent_soe"
    assert assessment.overall == 75.68
    assert assessment.fluency == 92
    assert assessment.completeness == 100
    assert assessment.words[0].word == "theme"
    assert assessment.words[0].phonemes[0].phoneme == "TH"
    assert assessment.issues[0].target == "theme"


def test_eval_mode_for_mode_maps_word_and_sentence() -> None:
    assert eval_mode_for_mode("word") == EVAL_MODE_WORD == "0"
    assert eval_mode_for_mode("sentence") == EVAL_MODE_SENTENCE == "1"
    assert eval_mode_for_mode(None) is None
    assert eval_mode_for_mode("paragraph") is None


def test_build_tencent_signed_url_honours_explicit_eval_mode(monkeypatch) -> None:
    monkeypatch.setenv("TENCENT_APP_ID", "123456")
    monkeypatch.setenv("TENCENT_SECRET_ID", "secret-id")
    monkeypatch.setenv("TENCENT_SECRET_KEY", "secret-key")
    monkeypatch.setenv("TENCENT_SOE_EVAL_MODE", "1")

    def signed(eval_mode):
        url = build_tencent_signed_url(
            ref_text="hello world",
            voice_format=1,
            timestamp=1000,
            nonce=42,
            voice_id="voice-1",
            eval_mode=eval_mode,
        )
        return parse_qs(urlsplit(url).query)["eval_mode"]

    assert signed("0") == ["0"]
    assert signed("1") == ["1"]
    # Falls back to the environment default when no explicit mode is given.
    assert signed(None) == ["1"]


def test_sentence_mode_overall_uses_accuracy_and_fluency_weighted_score() -> None:
    result = {
        "PronAccuracy": 70.0,
        "PronFluency": 0.8,
        "PronCompletion": 0.5,
        "Words": [{"Word": "meeting", "PronAccuracy": 70.0}],
    }
    assessment = TencentSOEProvider().map_result(
        result=result,
        reference_text="meeting",
        audio_file=None,
        eval_mode=EVAL_MODE_SENTENCE,
    )

    assert assessment.accuracy == 70
    assert assessment.fluency == 80
    assert assessment.completeness == 50
    assert assessment.overall == 74


def test_word_mode_result_leaves_fluency_and_completeness_unset() -> None:
    result = {
        "PronAccuracy": 72.0,
        "Words": [{"Word": "theme", "PronAccuracy": 72.0}],
    }
    assessment = TencentSOEProvider().map_result(
        result=result,
        reference_text="theme",
        audio_file=None,
        eval_mode=EVAL_MODE_WORD,
    )
    assert assessment.accuracy == 72
    # Word mode only exposes accuracy, so the weighted fallback has no other signal.
    assert assessment.overall == 72
    assert assessment.fluency is None
    assert assessment.completeness is None


def test_tencent_score_and_voice_format_helpers(tmp_path) -> None:
    wav = tmp_path / "sample.wav"
    wav.write_bytes(b"")
    assert infer_voice_format(wav) == 1
    assert normalize_tencent_score(0.5) == 50
    assert normalize_tencent_score(120) == 100
    assert normalize_tencent_score(None) == 0
