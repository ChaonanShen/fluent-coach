import base64
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.core.fixtures import load_generated_manifest
from backend.app.main import app
from backend.app.services.pronunciation import pronunciation_provider


def test_mock_pronunciation_provider_replays_speechocean_scores() -> None:
    item = load_generated_manifest("speechocean762")["items"][0]

    assessment = pronunciation_provider.assess(fixture_id=item["id"])

    assert assessment is not None
    assert assessment.provider == "mock"
    assert assessment.reference_text == item["transcript"]
    assert assessment.audio_file == item["audio_file"]
    assert assessment.overall == item["sentence_scores"]["total"] * 10
    assert assessment.words
    assert assessment.words[0].phonemes


def test_mock_pronunciation_provider_flags_low_scoring_words() -> None:
    item = load_generated_manifest("speechocean762")["items"][0]

    assessment = pronunciation_provider.assess(fixture_id=item["id"])

    assert assessment is not None
    low_words = {issue.target.lower() for issue in assessment.issues}
    assert "theme" in low_words


def test_pronunciation_assess_api_accepts_fixture_id() -> None:
    client = TestClient(app)
    item = load_generated_manifest("speechocean762")["items"][0]

    response = client.post(
        "/api/pronunciation/assess",
        json={"fixture_id": item["id"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "mock"
    assert body["reference_text"] == item["transcript"]
    assert body["words"]
    assert body["issues"]


def test_pronunciation_assess_api_accepts_audio_file() -> None:
    client = TestClient(app)
    item = load_generated_manifest("speechocean762")["items"][0]

    response = client.post(
        "/api/pronunciation/assess",
        json={
            "audio_file": item["audio_file"],
            "reference_text": item["transcript"],
        },
    )

    assert response.status_code == 200
    assert response.json()["audio_file"] == item["audio_file"]


def test_pronunciation_assess_upload_accepts_user_audio(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("APP_AUDIO_DIR", str(tmp_path))
    client = TestClient(app)
    item = load_generated_manifest("speechocean762")["items"][0]

    response = client.post(
        "/api/pronunciation/assess/upload",
        json={
            "reference_text": item["transcript"],
            "audio_base64": base64.b64encode(b"user-audio").decode("ascii"),
            "mime_type": "audio/webm",
        },
    )

    assert response.status_code == 200
    body = response.json()
    audio_path = Path(body["audio_file"])
    assert body["provider"] == "mock"
    assert body["reference_text"] == item["transcript"]
    assert audio_path.exists()
    assert audio_path.read_bytes() == b"user-audio"
    assert tmp_path in audio_path.parents


def test_pronunciation_assess_upload_rejects_invalid_base64() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/pronunciation/assess/upload",
        json={
            "reference_text": "THEN HE WENT TO THEME PARK",
            "audio_base64": "not-base64",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid audio_base64"


def test_pronunciation_assess_maps_provider_runtime_error(monkeypatch) -> None:
    class BrokenProvider:
        def assess(self, **kwargs):
            del kwargs
            raise RuntimeError("provider timeout")

    monkeypatch.setattr("backend.app.main.pronunciation_provider", BrokenProvider())
    client = TestClient(app)

    response = client.post(
        "/api/pronunciation/assess",
        json={"reference_text": "THEN HE WENT TO THEME PARK", "audio_file": "sample.wav"},
    )

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert detail["stage"] == "pronunciation"
    assert detail["code"] == "provider_request_failed"
    assert detail["user_message_zh"]


def test_pronunciation_assess_api_rejects_unknown_fixture() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/pronunciation/assess",
        json={"fixture_id": "not-found"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Pronunciation fixture not found"
