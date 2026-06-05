import json
import subprocess
import sys

from backend.app.eval.smoke import (
    _failed_real_check,
    render_smoke_markdown,
    run_fixture_smoke_report,
    run_real_smoke_report,
)


def test_fixture_smoke_report_uses_fake_providers() -> None:
    report = run_fixture_smoke_report()

    assert report["mode"] == "fixture_fake"
    assert report["external_services_used"] is False
    assert report["checks"]["asr"]["status"] == "passed"
    assert report["checks"]["asr"]["provider"] == "fake"
    assert report["checks"]["pronunciation"]["status"] == "passed"
    assert report["checks"]["pronunciation"]["provider"] == "mock"
    assert report["latency_ms"]["end_turn_to_asr_final"] is None


def test_smoke_report_renders_markdown() -> None:
    markdown = render_smoke_markdown(run_fixture_smoke_report())

    assert "# Smoke Report" in markdown
    assert "External services used: `false`" in markdown
    assert "end_turn -> asr.final" in markdown
    assert "Manual UI Checklist" in markdown


def test_real_smoke_report_skips_fake_providers() -> None:
    report = run_real_smoke_report()

    assert report["mode"] == "real_provider_smoke"
    assert report["external_services_used"] is False
    assert report["checks"]["llm"]["status"] == "skipped"
    assert report["checks"]["asr"]["status"] == "skipped"
    assert report["checks"]["pronunciation"]["status"] == "skipped"
    assert report["latency_ms"]["end_turn_to_asr_final"] is None


def test_real_smoke_report_renders_provider_status() -> None:
    markdown = render_smoke_markdown(run_real_smoke_report())

    assert "Mode: `real_provider_smoke`" in markdown
    assert "## Providers" in markdown
    assert "- LLM: fake" in markdown


def test_real_smoke_report_redacts_error_urls() -> None:
    check = _failed_real_check(
        provider="openai_compatible",
        started=0.0,
        exc=RuntimeError("request failed for https://example.test/v1/chat/completions with 401"),
    )

    assert "https://example.test" not in check["error"]
    assert "[redacted-url]" in check["error"]


def test_smoke_report_script_writes_outputs(tmp_path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_smoke_report.py",
            "--output-dir",
            str(tmp_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "smoke-latest.json" in completed.stdout
    report = json.loads((tmp_path / "smoke-latest.json").read_text(encoding="utf-8"))
    assert report["external_services_used"] is False
    assert (tmp_path / "smoke-latest.md").exists()


def test_smoke_report_script_writes_real_outputs(tmp_path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_smoke_report.py",
            "--mode",
            "real",
            "--output-dir",
            str(tmp_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "smoke-real-latest.json" in completed.stdout
    report = json.loads((tmp_path / "smoke-real-latest.json").read_text(encoding="utf-8"))
    assert report["mode"] == "real_provider_smoke"
    assert (tmp_path / "smoke-real-latest.md").exists()
