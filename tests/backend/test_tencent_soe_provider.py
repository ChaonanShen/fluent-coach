from urllib.parse import parse_qs, urlsplit

from backend.app.services.pronunciation import (
    TencentSOEProvider,
    build_tencent_signed_url,
    infer_voice_format,
    normalize_tencent_score,
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
    assert "signature" in query


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
    assert assessment.overall == 64.8
    assert assessment.fluency == 92
    assert assessment.completeness == 100
    assert assessment.words[0].word == "theme"
    assert assessment.words[0].phonemes[0].phoneme == "TH"
    assert assessment.issues[0].target == "theme"


def test_tencent_score_and_voice_format_helpers(tmp_path) -> None:
    wav = tmp_path / "sample.wav"
    wav.write_bytes(b"")
    assert infer_voice_format(wav) == 1
    assert normalize_tencent_score(0.5) == 50
    assert normalize_tencent_score(120) == 100
    assert normalize_tencent_score(None) == 0
