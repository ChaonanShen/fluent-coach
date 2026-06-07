from pydantic import TypeAdapter, ValidationError

from backend.app.core.fixtures import load_text_fixture
from backend.app.models import KnownInfoSource, Scenario, Session, SessionStatus, TurnSpeaker


def test_scenarios_fixture_parses_as_models() -> None:
    payload = load_text_fixture("scenarios")

    scenarios = TypeAdapter(list[Scenario]).validate_python(payload["scenarios"])

    assert len(scenarios) == 3
    assert {scenario.id for scenario in scenarios} == {
        "interview",
        "restaurant_ordering",
        "meeting",
    }
    assert scenarios[0].opening_line


def test_session_can_add_opening_and_user_turns() -> None:
    scenario = Scenario.model_validate(load_text_fixture("scenarios")["scenarios"][0])
    session = Session(scenario_id=scenario.id)

    opening_turn = session.add_turn(speaker=TurnSpeaker.AI, text=scenario.opening_line)
    user_turn = session.add_turn(
        speaker=TurnSpeaker.USER,
        text="I have worked on backend systems for three years.",
        asr_confidence=0.91,
    )

    assert session.status == SessionStatus.ACTIVE
    assert opening_turn.session_id == session.id
    assert user_turn.asr_confidence == 0.91
    assert [turn.speaker for turn in session.turns] == [TurnSpeaker.AI, TurnSpeaker.USER]


def test_session_end_sets_status_and_timestamp() -> None:
    session = Session(scenario_id="interview")

    session.end()

    assert session.status == SessionStatus.ENDED
    assert session.ended_at is not None


def test_session_can_store_known_info() -> None:
    session = Session(
        scenario_id="interview",
        known_info_text="  Backend engineer with API and product planning experience.  ",
        known_info_sources=[
            KnownInfoSource(
                name="resume.pdf",
                kind="pdf",
                text_preview="Backend engineer",
                char_count=38,
            )
        ],
    )

    assert session.known_info_text == "Backend engineer with API and product planning experience."
    assert session.known_info_sources[0].name == "resume.pdf"
    assert session.known_info_sources[0].kind == "pdf"


def test_blank_known_info_normalizes_to_none() -> None:
    session = Session(scenario_id="interview", known_info_text="   ")

    assert session.known_info_text is None
    assert session.known_info_sources == []


def test_turn_rejects_invalid_confidence() -> None:
    session = Session(scenario_id="interview")

    try:
        session.add_turn(speaker=TurnSpeaker.USER, text="hello", asr_confidence=1.5)
    except ValidationError as exc:
        assert "less than or equal to 1" in str(exc)
    else:
        raise AssertionError("Expected invalid ASR confidence to fail validation")


def test_session_models_expose_json_schema() -> None:
    scenario_schema = Scenario.model_json_schema()
    session_schema = Session.model_json_schema()

    assert scenario_schema["type"] == "object"
    assert "opening_line" in scenario_schema["properties"]
    assert session_schema["type"] == "object"
    assert "turns" in session_schema["properties"]
