from fastapi.testclient import TestClient

from backend.app.testkit.dashboard import dashboard_app
from backend.app.testkit.models import RunRecord, TurnRecord
from backend.app.testkit.run_store import save_run


def test_bench_dashboard_serves_runs_and_audio(monkeypatch, tmp_path) -> None:
    runs_dir = tmp_path / "runs"
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir()
    audio_path = audio_dir / "turn.wav"
    audio_path.write_bytes(b"fake-audio")
    monkeypatch.setenv("BENCH_RUNS_DIR", str(runs_dir))
    monkeypatch.setenv("APP_AUDIO_DIR", str(audio_dir))
    save_run(
        RunRecord(
            run_id="dashboard-run",
            scenario_id="interview",
            mode="offline_fake",
            generated_at="2026-06-06T00:00:00+00:00",
            providers={"llm": "fake"},
            turns=[
                TurnRecord(
                    index=0,
                    user_text="hello",
                    asr_text="hello",
                    expected_text="hello",
                    audio_path=str(audio_path),
                    interviewer_text="Good morning. Could you introduce yourself?",
                    reply_text="hi",
                    clean_text="I have three years of experience.",
                    injected_text="I has three year experience.",
                    expected_corrected_text="I have three years of experience.",
                    expected_error_types=["subject_verb_agreement", "plural_noun"],
                    grammar_metrics={"expected_error_recall": 1.0, "corrected_text_match": True},
                    tts={"provider": "fake_audio", "voice": "test"},
                    timings_ms={"reply_first_delta_ms": 1.0, "tts_ms": 2.0},
                    wer=0.0,
                )
            ],
        )
    )

    client = TestClient(dashboard_app)

    index = client.get("/")
    assert index.status_code == 200
    assert "面试官" in index.text
    assert "面试者" in index.text
    assert "服务员" in index.text
    assert "顾客" in index.text
    assert "项目负责人" in index.text
    assert "团队成员" in index.text
    runs = client.get("/api/runs")
    assert runs.status_code == 200
    assert runs.json()[0]["run_id"] == "dashboard-run"
    detail = client.get("/api/runs/dashboard-run")
    assert detail.status_code == 200
    assert detail.json()["turns"][0]["reply_text"] == "hi"
    assert detail.json()["turns"][0]["interviewer_text"] == "Good morning. Could you introduce yourself?"
    assert detail.json()["turns"][0]["injected_text"] == "I has three year experience."
    assert detail.json()["turns"][0]["grammar_metrics"]["expected_error_recall"] == 1.0
    audio = client.get("/api/runs/dashboard-run/turns/0/audio")
    assert audio.status_code == 200
    assert audio.content == b"fake-audio"


def test_bench_dashboard_rejects_audio_outside_allowed_roots(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("BENCH_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("APP_AUDIO_DIR", str(tmp_path / "audio"))
    save_run(
        RunRecord(
            run_id="bad-audio-run",
            scenario_id="interview",
            mode="offline_fake",
            generated_at="2026-06-06T00:00:00+00:00",
            providers={},
            turns=[
                TurnRecord(
                    index=0,
                    user_text="hello",
                    asr_text="hello",
                    audio_path="/etc/passwd",
                    reply_text="hi",
                )
            ],
        )
    )

    client = TestClient(dashboard_app)

    assert client.get("/api/runs/bad-audio-run/turns/0/audio").status_code == 404
