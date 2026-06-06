from __future__ import annotations

from itertools import cycle, islice

from pydantic import BaseModel, ConfigDict, Field


class GrammarErrorCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str = Field(min_length=1)
    clean_text: str = Field(min_length=1)
    injected_text: str = Field(min_length=1)
    expected_corrected_text: str = Field(min_length=1)
    expected_error_types: list[str] = Field(min_length=1)
    error_spans: list[str] = Field(default_factory=list)


GRAMMAR_ERROR_CASES: tuple[GrammarErrorCase, ...] = (
    GrammarErrorCase(
        scenario_id="interview",
        clean_text="I have three years of experience in backend development.",
        injected_text="I has three year experience in backend development.",
        expected_corrected_text="I have three years of experience in backend development.",
        expected_error_types=["subject_verb_agreement", "plural_noun"],
        error_spans=["I has", "three year"],
    ),
    GrammarErrorCase(
        scenario_id="interview",
        clean_text="Yesterday I went to a meeting and explained the risk.",
        injected_text="Yesterday I go to meeting and explain the risk.",
        expected_corrected_text="Yesterday I went to a meeting and explained the risk.",
        expected_error_types=["verb_tense", "article"],
        error_spans=["I go", "to meeting"],
    ),
    GrammarErrorCase(
        scenario_id="interview",
        clean_text="One challenge I faced was communicating the trade-offs clearly.",
        injected_text="One challenge I face was communicate the trade-offs clearly.",
        expected_corrected_text="One challenge I faced was communicating the trade-offs clearly.",
        expected_error_types=["verb_tense", "gerund"],
        error_spans=["I face", "was communicate"],
    ),
    GrammarErrorCase(
        scenario_id="restaurant_ordering",
        clean_text="Could I have the chicken sandwich and a glass of water, please?",
        injected_text="Could I has the chicken sandwich and glass of water, please?",
        expected_corrected_text="Could I have the chicken sandwich and a glass of water, please?",
        expected_error_types=["modal_verb", "article"],
        error_spans=["I has", "and glass"],
    ),
    GrammarErrorCase(
        scenario_id="restaurant_ordering",
        clean_text="I would like a salad without onions because I have an allergy.",
        injected_text="I would like salad without onion because I has an allergy.",
        expected_corrected_text="I would like a salad without onions because I have an allergy.",
        expected_error_types=["article", "plural_noun", "subject_verb_agreement"],
        error_spans=["like salad", "I has"],
    ),
    GrammarErrorCase(
        scenario_id="meeting",
        clean_text="I finished the API review and shared the remaining questions.",
        injected_text="I finish the API review and share the remaining questions.",
        expected_corrected_text="I finished the API review and shared the remaining questions.",
        expected_error_types=["verb_tense"],
        error_spans=["I finish", "and share"],
    ),
    GrammarErrorCase(
        scenario_id="meeting",
        clean_text="The biggest risk is that the design decision is still open.",
        injected_text="The biggest risk are that design decision is still open.",
        expected_corrected_text="The biggest risk is that the design decision is still open.",
        expected_error_types=["subject_verb_agreement", "article"],
        error_spans=["risk are", "that design"],
    ),
)


def grammar_cases_for_scenario(scenario_id: str) -> tuple[GrammarErrorCase, ...]:
    cases = tuple(case for case in GRAMMAR_ERROR_CASES if case.scenario_id == scenario_id)
    if not cases:
        raise ValueError(f"No grammar error cases for scenario: {scenario_id}")
    return cases


def grammar_case_sequence(scenario_id: str, turns: int) -> list[GrammarErrorCase]:
    if turns < 0:
        raise ValueError("turns must be non-negative")
    return list(islice(cycle(grammar_cases_for_scenario(scenario_id)), turns))
