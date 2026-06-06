from backend.app.services.custom_scenarios import CustomScenarioBuilder, contains_cjk


def test_custom_scenario_builder_matches_airport_prompt() -> None:
    scenario = CustomScenarioBuilder().build("airport check-in")

    assert scenario.id.startswith("custom_")
    assert scenario.name == "Airport Check-in"
    assert scenario.ai_role == "Airline check-in agent"
    assert scenario.user_role == "Passenger checking in for a flight"
    assert scenario.opening_line == "Hello. Where are you flying today?"
    assert scenario.conversation_goals
    assert scenario.target_expressions
    assert scenario.correction_focus
    assert scenario.summary_rubric


def test_custom_scenario_builder_uses_custom_name() -> None:
    scenario = CustomScenarioBuilder().build(
        "I want to practice checking in at a hotel with a reservation problem.",
        name="Hotel check-in",
    )

    assert scenario.name == "Hotel check-in"
    assert scenario.ai_role == "Hotel front desk clerk"
    assert scenario.user_role == "Hotel guest checking in and handling a reservation issue"
    assert scenario.opening_line.startswith("Good evening.")


def test_custom_scenario_builder_matches_chinese_doctor_prompt_in_english() -> None:
    scenario = CustomScenarioBuilder().build("我希望你扮演一位医生，我向你问诊")

    assert scenario.name == "Doctor Consultation"
    assert "Doctor" in scenario.ai_role
    assert "Patient" in scenario.user_role
    assert scenario.opening_line == "Good morning. What symptoms have you been having?"
    assert not contains_cjk(scenario.model_dump_json())


def test_custom_scenario_builder_uses_english_generic_fallback() -> None:
    scenario = CustomScenarioBuilder().build("我想练习一个很特别的生活场景")

    assert scenario.name == "Custom Role Play"
    assert scenario.ai_role == "Conversation partner in a custom English speaking role-play"
    assert scenario.opening_line == "Let's start the role-play. What would you like to say first?"
    assert not contains_cjk(scenario.model_dump_json())


def test_custom_scenario_builder_ignores_chinese_custom_name() -> None:
    scenario = CustomScenarioBuilder().build(
        "我希望你扮演一位医生，我向你问诊",
        name="医生问诊",
    )

    assert scenario.name == "Doctor Consultation"
    assert not contains_cjk(scenario.model_dump_json())
