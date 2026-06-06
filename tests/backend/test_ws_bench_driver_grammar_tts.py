import base64

from backend.app.models import CorrectionTiming, GrammarCorrection, GrammarIssue, GrammarSeverity
from backend.app.services.analysis import analysis_store
from backend.app.services.asr import FakeASR
from backend.app.services.dialogue import DialogueService
from backend.app.services.llm import FakeLLMClient
from backend.app.services.sessions import session_store
from backend.app.services.tts import TTSResult
from backend.app.testkit.ws_driver import run_ws_conversation


class FakeAudioTTS:
    provider_name = "fake_audio"
    voice = "voice-test"

    def synthesize(self, text: str) -> TTSResult:
        return TTSResult(
            provider=self.provider_name,
            text=text,
            audio_url=None,
            audio_base64=base64.b64encode(b"fake-wav-audio").decode("ascii"),
            mime_type="audio/wav",
            fallback_applied=False,
        )


class GrammarForInjectedErrors:
    def check(self, *, scenario_id, user_text, conversation_context=None):
        del conversation_context
        issues = []
        corrected = user_text
        if "has" in user_text:
            issues.append(_issue("subject_verb_agreement", "has", "have"))
            corrected = corrected.replace(" has ", " have ", 1)
        if "three year" in user_text:
            issues.append(_issue("plural_noun", "three year", "three years"))
            corrected = corrected.replace("three year", "three years", 1)
        if "I go" in user_text:
            issues.append(_issue("verb_tense", "I go", "I went"))
            corrected = corrected.replace("I go", "I went", 1)
        if "to meeting" in user_text:
            issues.append(_issue("article", "to meeting", "to a meeting"))
            corrected = corrected.replace("to meeting", "to a meeting", 1)
        return GrammarCorrection(
            scenario_id=scenario_id,
            user_text=user_text,
            corrected_text=corrected,
            issues=issues,
            overall_severity=GrammarSeverity.MINOR,
            correction_timing=CorrectionTiming.DELAYED_SUMMARY,
        )


def test_ws_bench_driver_records_grammar_tts_turns(monkeypatch, tmp_path) -> None:
    session_store.clear()
    analysis_store.clear()
    monkeypatch.setenv("APP_AUDIO_DIR", str(tmp_path / "audio"))
    monkeypatch.setenv("BENCH_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setattr("backend.app.main.asr_provider", FakeASR())
    monkeypatch.setattr(
        "backend.app.main.dialogue_service",
        DialogueService(FakeLLMClient(responses=["That is useful. What result did you get?"])),
    )
    monkeypatch.setattr("backend.app.main.grammar_service", GrammarForInjectedErrors())

    turns = run_ws_conversation(
        scenario_id="interview",
        turns=2,
        mode="grammar_tts",
        tts_provider=FakeAudioTTS(),
        allow_fake_providers=True,
    )

    assert len(turns) == 2
    for turn in turns:
        assert turn.clean_text
        assert turn.injected_text
        assert turn.injected_text == turn.expected_text == turn.asr_text
        assert turn.expected_corrected_text
        assert turn.expected_error_types
        assert turn.tts["provider"] == "fake_audio"
        assert turn.tts["voice"] == "voice-test"
        assert turn.timings_ms["tts_ms"] >= 0
        assert turn.timings_ms["reply_first_delta_ms"] >= 0
        assert turn.grammar is not None
        assert turn.grammar_metrics["expected_error_recall"] == 1.0
        assert turn.grammar_metrics["asr_preserved_injected_error"] is True


def _issue(error_type: str, original: str, corrected: str) -> GrammarIssue:
    return GrammarIssue(
        error_type=error_type,
        original_span=original,
        corrected_span=corrected,
        severity=GrammarSeverity.MINOR,
        explanation_zh="测试错误。",
    )
