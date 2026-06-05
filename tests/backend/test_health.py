from fastapi.testclient import TestClient

from backend.app.main import app


def test_health_reports_ready_fixtures() -> None:
    client = TestClient(app)

    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["fixtures"]["ready"] is True
    assert body["providers"]["llm_provider"] == "fake"
    assert body["providers"]["llm_model"] is None
    assert body["providers"]["asr_provider"] == "fake"
    assert body["providers"]["pronunciation_provider"] == "mock"
    assert body["providers"]["tts_provider"] == "browser"
    assert body["providers"]["external_services_enabled"] is False
