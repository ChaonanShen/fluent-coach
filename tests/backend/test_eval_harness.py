from backend.app.eval.harness import (
    evaluate_asr,
    evaluate_grammar,
    evaluate_pronunciation,
    render_markdown,
    run_all_evaluations,
)
from backend.app.eval.metrics import corpus_wer, pearson_correlation, sentence_gleu, word_error_rate


def test_metric_helpers_compute_expected_values() -> None:
    assert word_error_rate("hello world", "hello world") == 0
    assert word_error_rate("hello world", "hello") == 0.5
    assert corpus_wer([("hello world", "hello"), ("a b", "a b")]) == 0.25
    assert sentence_gleu("hello world", ["hello world"]) > 0.99
    assert pearson_correlation([1, 2, 3], [2, 4, 6]) > 0.99


def test_eval_harness_returns_fixture_backed_metrics() -> None:
    asr = evaluate_asr()
    grammar = evaluate_grammar()
    pronunciation = evaluate_pronunciation()

    assert asr["librispeech_count"] == 30
    assert asr["librispeech_wer"] == 0
    assert asr["l2_arctic_count"] == 45
    assert asr["l2_arctic_manual_annotation_rate"] > 0
    assert asr["l2_arctic_native_language_counts"]
    assert grammar["jfleg_count"] == 160
    assert grammar["schema_pass_rate"] == 1
    assert pronunciation["speechocean_count"] == 45
    assert pronunciation["provider_return_rate"] == 1
    assert pronunciation["sentence_total_correlation"] > 0.99
    assert pronunciation["sentence_total_mae"] == 0


def test_eval_report_renders_markdown() -> None:
    report = run_all_evaluations()
    markdown = render_markdown(report)

    assert "# Evaluation Report" in markdown
    assert "LibriSpeech WER" in markdown
    assert "L2-ARCTIC manual annotation rate" in markdown
    assert "GLEU" in markdown
    assert "Sentence total correlation" in markdown
