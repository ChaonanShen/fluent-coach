from backend.app.services.llm import FakeLLMClient
from backend.app.testkit.grammar_cases import grammar_case_sequence, grammar_cases_for_scenario
from backend.app.testkit.grammar_injection import inject_errors, next_error_case, score_grammar_result
from backend.app.testkit.virtual_user import LLMVirtualUser, TemplateVirtualUser


def test_grammar_cases_rotate_by_scenario() -> None:
    cases = grammar_case_sequence("interview", 4)

    assert len(cases) == 4
    assert cases[0].scenario_id == "interview"
    assert cases[0] == next_error_case("interview", 0)
    assert cases[0] == cases[3]
    assert cases[0].injected_text != cases[0].clean_text
    assert cases[0].expected_error_types


def test_grammar_cases_reject_unknown_scenario() -> None:
    try:
        grammar_cases_for_scenario("unknown")
    except ValueError as exc:
        assert "No grammar error cases" in str(exc)
    else:
        raise AssertionError("unknown scenario should fail")


def test_score_grammar_result_counts_error_type_recall_and_correction_match() -> None:
    case = next_error_case("interview", 0)
    grammar = {
        "corrected_text": "I have three years of experience in backend development.",
        "issues": [
            {"error_type": "agreement"},
            {"error_type": "number"},
        ],
    }

    metrics = score_grammar_result(case, grammar, "I has three year experience in backend development.")

    assert metrics["expected_error_recall"] == 1.0
    assert metrics["matched_error_types"] == ["plural_noun", "subject_verb_agreement"]
    assert metrics["corrected_text_match"] is True
    assert metrics["asr_preserved_injected_error"] is True


def test_score_grammar_result_normalizes_real_provider_error_type_names() -> None:
    case = next_error_case("interview", 2)
    grammar = {
        "corrected_text": "One challenge I faced was communicating the trade-offs clearly.",
        "issues": [
            {"error_type": "tense_mismatch"},
            {"error_type": "verb_form_error"},
        ],
    }

    metrics = score_grammar_result(
        case,
        grammar,
        "One challenge I face was communicate the trade-offs clearly.",
    )

    assert metrics["expected_error_recall"] == 1.0
    assert metrics["matched_error_types"] == ["gerund", "verb_tense"]


def test_score_grammar_result_matches_compound_real_provider_error_type() -> None:
    case = next_error_case("interview", 0)
    grammar = {
        "corrected_text": "I have three years of experience in backend development.",
        "issues": [
            {"error_type": "subject-verb agreement and noun number"},
        ],
    }

    metrics = score_grammar_result(case, grammar, "I has three year experience in backend development.")

    assert metrics["expected_error_recall"] == 1.0
    assert metrics["matched_error_types"] == ["plural_noun", "subject_verb_agreement"]


def test_inject_errors_derives_case_from_clean_text() -> None:
    case = inject_errors(
        "I have three years of experience and finished a platform project.",
        scenario_id="interview",
        index=0,
    )

    assert case.clean_text == "I have three years of experience and finished a platform project."
    assert case.injected_text == "I has three year of experience and finish platform project."
    assert case.expected_corrected_text == case.clean_text
    assert case.expected_error_types == [
        "subject_verb_agreement",
        "plural_noun",
        "verb_tense",
        "article",
    ]


def test_score_grammar_result_handles_missing_grammar() -> None:
    case = next_error_case("meeting", 0)

    metrics = score_grammar_result(case, None, "I finished the API review.")

    assert metrics["expected_error_recall"] == 0.0
    assert metrics["matched_error_types"] == []
    assert metrics["corrected_text_match"] is False
    assert metrics["asr_preserved_injected_error"] is False


def test_template_virtual_user_returns_clean_case_text() -> None:
    user = TemplateVirtualUser()

    assert user.next_clean_turn(scenario_id="interview", history=[], index=0) == next_error_case(
        "interview",
        0,
    ).clean_text


def test_llm_virtual_user_falls_back_for_too_short_reply() -> None:
    user = LLMVirtualUser(FakeLLMClient(responses=["ok"]))

    assert user.next_clean_turn(scenario_id="interview", history=[], index=0) == next_error_case(
        "interview",
        0,
    ).clean_text


def test_llm_virtual_user_uses_clean_llm_sentence() -> None:
    user = LLMVirtualUser(FakeLLMClient(responses=["I recently improved a reporting API for my team."]))

    assert user.next_clean_turn(scenario_id="interview", history=[], index=0) == (
        "I recently improved a reporting API for my team."
    )
