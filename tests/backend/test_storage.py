from backend.app.models import (
    AnalysisError,
    AnalysisErrorSeverity,
    AnalysisStage,
    GrammarCorrection,
    GrammarIssue,
    GrammarSeverity,
    MistakeItem,
    MistakeSourceStage,
    MistakeType,
    PronunciationAssessment,
    Session,
    TurnSpeaker,
)
from backend.app.services.storage import SQLiteLogStore


def test_sqlite_log_store_persists_session_and_turns(tmp_path) -> None:
    store = SQLiteLogStore(tmp_path / "test.sqlite")
    session = Session(scenario_id="interview")
    session.add_turn(speaker=TurnSpeaker.AI, text="Hello")
    session.add_turn(speaker=TurnSpeaker.USER, text="I am ready.")

    store.save_session(session)

    restored = store.get_session(session.id)
    assert restored is not None
    assert restored.id == session.id
    assert len(restored.turns) == 2
    assert [turn.text for turn in store.list_turns(session.id)] == ["Hello", "I am ready."]


def test_sqlite_log_store_persists_analysis_outputs(tmp_path) -> None:
    store = SQLiteLogStore(tmp_path / "test.sqlite")
    correction = GrammarCorrection(
        scenario_id="interview",
        user_text="I am interest this role.",
        corrected_text="I am interested in this role.",
        issues=[
            GrammarIssue(
                error_type="word_choice",
                original_span="interest",
                corrected_span="interested",
                severity=GrammarSeverity.MAJOR,
                explanation_zh="这里需要形容词 interested。",
            )
        ],
        overall_severity=GrammarSeverity.MAJOR,
        correction_timing="after_turn",
    )
    assessment = PronunciationAssessment(
        provider="mock",
        reference_text="HELLO",
        overall=80,
        accuracy=80,
        fluency=75,
    )
    mistake = MistakeItem(
        type=MistakeType.GRAMMAR,
        session_id="session_1",
        turn_id="turn_1",
        source_stage=MistakeSourceStage.GRAMMAR,
        source_id=correction.id,
        subtype="word_choice",
        severity=GrammarSeverity.MAJOR,
        tags=["interview", "word_choice"],
        wrong="I am interest this role.",
        correct="I am interested in this role.",
        explanation_zh="这里需要形容词 interested。",
        practice_sentence="I am interested in this role.",
    )
    error = AnalysisError(
        stage=AnalysisStage.PRONUNCIATION,
        code="provider_timeout",
        user_message_zh="发音评测暂时超时。",
        severity=AnalysisErrorSeverity.WARNING,
        fallback_applied=True,
    )

    store.save_grammar_correction(correction)
    store.save_pronunciation_assessment(assessment)
    store.save_mistake_item(mistake)
    store.save_analysis_error(error)

    assert store.count_rows("grammar_corrections") == 1
    assert store.count_rows("pronunciation_assessments") == 1
    assert store.count_rows("mistake_items") == 1
    assert store.count_rows("analysis_errors") == 1
    restored_mistake = store.list_mistake_items(session_id="session_1")[0]
    assert restored_mistake.id == mistake.id
    assert restored_mistake.turn_id == "turn_1"
    assert restored_mistake.source_stage == MistakeSourceStage.GRAMMAR
    assert restored_mistake.subtype == "word_choice"
    assert store.list_mistake_items(session_id="missing") == []
