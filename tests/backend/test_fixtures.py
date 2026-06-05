from pathlib import Path

from backend.app.core.fixtures import (
    GENERATED_MANIFESTS,
    PROJECT_ROOT,
    load_all_generated_manifests,
    load_text_fixture,
    read_json,
    resolve_fixture_audio,
)


def test_generated_manifest_counts_match_summary() -> None:
    summary = read_json(PROJECT_ROOT / "fixtures/generated/dataset_subset_summary.json")
    manifests = load_all_generated_manifests()

    assert summary["missing_or_empty"] == []
    for name, manifest in manifests.items():
        assert manifest["count"] == summary["counts"][name]
        assert manifest["count"] == len(manifest["items"])


def test_generated_audio_files_exist() -> None:
    manifests = load_all_generated_manifests()

    checked_audio = 0
    for manifest in manifests.values():
        for item in manifest["items"]:
            audio_file = item.get("audio_file")
            if not audio_file:
                continue
            audio_path = resolve_fixture_audio(audio_file)
            assert audio_path.exists(), f"missing fixture audio: {audio_path}"
            assert audio_path.is_file()
            checked_audio += 1

    assert checked_audio == 120


def test_text_fixtures_have_expected_shapes() -> None:
    scenarios = load_text_fixture("scenarios")
    grammar = load_text_fixture("grammar_expression_errors")
    dialogues = load_text_fixture("dialogue_samples")

    scenario_ids = {item["id"] for item in scenarios["scenarios"]}
    assert scenario_ids == {"interview", "restaurant_ordering", "meeting"}
    for scenario in scenarios["scenarios"]:
        assert scenario["opening_line"]
        assert scenario["conversation_goals"]
        assert scenario["target_expressions"]
        assert scenario["correction_focus"]
        assert scenario["summary_rubric"]

    assert len(grammar["items"]) == 20
    for item in grammar["items"]:
        assert item["scenario_id"] in scenario_ids
        assert item["error_span"] in item["original_text"]
        assert item["severity"] in {"minor", "major"}
        assert item["correction_timing"] in {
            "immediate_light",
            "after_turn",
            "delayed_summary",
        }

    assert len(dialogues["samples"]) == 10
    for sample in dialogues["samples"]:
        assert sample["scenario_id"] in scenario_ids
        assert len(sample["turns"]) >= 3
        assert {turn["speaker"] for turn in sample["turns"]} <= {"ai", "user"}


def test_all_manifest_paths_are_registered() -> None:
    expected = {
        "librispeech",
        "speechocean762",
        "l2_arctic",
        "jfleg",
    }

    assert set(GENERATED_MANIFESTS) == expected
    for path in GENERATED_MANIFESTS.values():
        assert isinstance(path, Path)
        assert path.exists()
