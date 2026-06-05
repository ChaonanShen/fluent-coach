from backend.app.eval.harness import (
    evaluate_asr,
    evaluate_grammar,
    evaluate_pronunciation,
    render_markdown,
    run_all_evaluations,
)
from backend.app.eval.l2_arctic import summarize_l2_arctic_annotations, textgrid_stats
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
    assert asr["l2_arctic_annotation_stats"]["annotated_manifest_count"] > 0
    assert (
        asr["l2_arctic_annotation_stats"]["available_annotation_count"]
        <= asr["l2_arctic_annotation_stats"]["annotated_manifest_count"]
    )
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
    assert "L2-ARCTIC TextGrid files available" in markdown
    assert "L2-ARCTIC mispronunciation hit rate" in markdown
    assert "GLEU" in markdown
    assert "Sentence total correlation" in markdown


def test_textgrid_stats_count_labels_and_issue_markers(tmp_path) -> None:
    textgrid = tmp_path / "sample.TextGrid"
    textgrid.write_text(
        """
        intervals [1]:
            xmin = 0
            xmax = 0.1
            text = "sil"
        intervals [2]:
            xmin = 0.1
            xmax = 0.2
            text = "AA"
        intervals [3]:
            xmin = 0.2
            xmax = 0.3
            text = "TH->S"
        """,
        encoding="utf-8",
    )

    stats = textgrid_stats(textgrid)

    assert stats.interval_count == 3
    assert stats.non_empty_label_count == 2
    assert stats.suspected_issue_count == 1


def test_l2_arctic_annotation_summary_reports_available_textgrids(tmp_path) -> None:
    annotation_dir = tmp_path / "dataset" / "extracted" / "l2_arctic" / "ABC" / "annotation"
    annotation_dir.mkdir(parents=True)
    (annotation_dir / "arctic_a0001.TextGrid").write_text('text = "AA->AE"\n', encoding="utf-8")
    items = [
        {
            "annotation_file": "dataset/extracted/l2_arctic/ABC/annotation/arctic_a0001.TextGrid",
            "has_manual_annotation": True,
        },
        {
            "annotation_file": "dataset/extracted/l2_arctic/ABC/annotation/missing.TextGrid",
            "has_manual_annotation": True,
        },
    ]

    summary = summarize_l2_arctic_annotations(items, project_root=tmp_path)

    assert summary["annotated_manifest_count"] == 2
    assert summary["available_annotation_count"] == 1
    assert summary["parsed_interval_count"] == 1
    assert summary["suspected_issue_label_count"] == 1
    assert summary["hit_rate_status"] == "not_computed_no_detector"
