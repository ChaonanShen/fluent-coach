from pydantic import ValidationError

from backend.app.core.fixtures import load_generated_manifest, load_text_fixture
from backend.app.models import (
    AnalysisError,
    AnalysisErrorSeverity,
    AnalysisStage,
    CorrectionTiming,
    GrammarCorrection,
    GrammarIssue,
    MistakeItem,
    MistakeType,
    PhonemeScore,
    PronunciationAssessment,
    PronunciationWordScore,
    SessionSummary,
)


def test_grammar_fixture_maps_to_correction_model() -> None:
    item = load_text_fixture("grammar_expression_errors")["items"][0]

    correction = GrammarCorrection(
        scenario_id=item["scenario_id"],
        user_text=item["original_text"],
        corrected_text=item["expected_corrected_text"],
        better_expression=item["better_expression"],
        issues=[
            GrammarIssue(
                error_type=error_type,
                original_span=item["error_span"],
                corrected_span=item["expected_corrected_text"],
                severity=item["severity"],
                explanation_zh=item["explanation_zh"],
            )
            for error_type in item["error_types"]
        ],
        overall_severity=item["severity"],
        correction_timing=item["correction_timing"],
    )

    assert correction.correction_timing == CorrectionTiming.AFTER_TURN
    assert correction.issues
    assert correction.issues[0].original_span in correction.user_text


def test_speechocean_fixture_maps_to_pronunciation_assessment() -> None:
    item = load_generated_manifest("speechocean762")["items"][0]
    sentence_scores = item["sentence_scores"]
    word_scores = []
    for word in item["word_scores"]:
        word_scores.append(
            PronunciationWordScore(
                word=word["text"],
                accuracy=float(word["accuracy"]) * 10,
                phonemes=[
                    PhonemeScore(phoneme=phone, accuracy=float(score) * 50)
                    for phone, score in zip(word["phones"], word["phones-accuracy"], strict=True)
                ],
            )
        )

    assessment = PronunciationAssessment(
        provider="mock",
        reference_text=item["transcript"],
        audio_file=item["audio_file"],
        overall=float(sentence_scores["total"]) * 10,
        accuracy=float(sentence_scores["accuracy"]) * 10,
        fluency=float(sentence_scores["fluency"]) * 10,
        prosody=float(sentence_scores["prosodic"]) * 10,
        completeness=float(sentence_scores["completeness"]) * 10,
        words=word_scores,
    )

    assert assessment.provider == "mock"
    assert assessment.words[0].phonemes
    assert 0 <= assessment.overall <= 100


def test_analysis_error_uses_canonical_stage_and_message() -> None:
    error = AnalysisError(
        stage=AnalysisStage.PRONUNCIATION,
        code="provider_timeout",
        user_message_zh="发音评测暂时超时，已保留本轮对话。",
        severity=AnalysisErrorSeverity.WARNING,
        fallback_applied=True,
        provider="tencent_soe",
        raw_code="timeout",
    )

    assert error.stage == AnalysisStage.PRONUNCIATION
    assert error.fallback_applied is True


def test_analysis_error_rejects_unknown_stage() -> None:
    try:
        AnalysisError(
            stage="billing",
            code="bad_stage",
            user_message_zh="未知阶段。",
            severity=AnalysisErrorSeverity.ERROR,
            fallback_applied=False,
        )
    except ValidationError as exc:
        assert "asr" in str(exc)
    else:
        raise AssertionError("Expected unknown analysis stage to fail validation")


def test_summary_and_mistake_models_expose_learning_loop_fields() -> None:
    summary = SessionSummary(
        session_id="session_1",
        grammar_score=82,
        pronunciation_score=None,
        fluency_score=76,
        vocabulary_score=79,
        task_completion_rate=0.6,
        top_issues=["past tense", "final consonants"],
        next_drills=["Repeat three interview answers"],
    )
    mistake = MistakeItem(
        type=MistakeType.GRAMMAR,
        wrong="I am interest this role.",
        correct="I am interested in this role.",
        explanation_zh="这里需要形容词 interested，并搭配介词 in。",
        practice_sentence="I am very interested in this role.",
        mastery=0.2,
    )

    assert summary.pronunciation_score is None
    assert summary.task_completion_rate == 0.6
    assert mistake.review_count == 0
    assert mistake.type == MistakeType.GRAMMAR


def test_analysis_models_expose_json_schema() -> None:
    assert "corrected_text" in GrammarCorrection.model_json_schema()["properties"]
    assert "words" in PronunciationAssessment.model_json_schema()["properties"]
    assert "fallback_applied" in AnalysisError.model_json_schema()["properties"]
