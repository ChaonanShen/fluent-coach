from backend.app.services.analysis import analysis_store
from backend.app.services.sessions import session_store
from backend.app.testkit.report import aggregate_latency, build_run_record
from backend.app.testkit.run_store import load_run, save_run
from backend.app.testkit.ws_driver import run_ws_conversation


def test_ws_bench_driver_records_streaming_turns(monkeypatch, tmp_path) -> None:
    session_store.clear()
    analysis_store.clear()
    monkeypatch.setenv("APP_AUDIO_DIR", str(tmp_path / "audio"))
    monkeypatch.setenv("BENCH_RUNS_DIR", str(tmp_path / "runs"))

    turns = run_ws_conversation(scenario_id="interview", turns=3)

    assert len(turns) == 3
    for turn in turns:
        assert turn.expected_text == turn.asr_text
        assert turn.wer == 0
        assert turn.reply_text
        assert turn.audio_path is not None
        assert turn.grammar is not None
        assert turn.timings_ms["reply_first_delta_ms"] >= 0
        assert turn.timings_ms["reply_itl_ms"] >= 0
        assert turn.timings_ms["reply_delta_count"] >= 2
        assert turn.timings_ms["dialogue_reply_ms"] >= 0
        assert turn.timings_ms["grammar_ms"] >= 0

    summary = aggregate_latency(turns)
    assert summary["reply_first_delta_ms"].count == 3
    assert summary["reply_first_delta_ms"].p50 >= 0
    assert summary["reply_first_delta_ms"].p90 >= 0

    run = build_run_record(
        run_id="test-run",
        scenario_id="interview",
        mode="offline_fake",
        generated_at="2026-06-06T00:00:00+00:00",
        providers={"llm": "fake", "asr": "fake", "pronunciation": "mock"},
        turns=turns,
    )
    path = save_run(run)
    loaded = load_run("test-run")

    assert path.name == "test-run.json"
    assert loaded.run_id == run.run_id
    assert len(loaded.turns) == 3
    assert loaded.latency_summary["grammar_ms"].count == 3
