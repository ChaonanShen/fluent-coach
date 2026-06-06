from backend.app.services.custom_scenarios import CustomScenarioBuilder


def test_custom_scenario_builder_generates_valid_scenario() -> None:
    scenario = CustomScenarioBuilder().build("airport check-in")

    assert scenario.id.startswith("custom_")
    assert scenario.name == "airport check-in"
    assert scenario.ai_role == "Conversation partner"
    assert scenario.user_role == "Learner practicing: airport check-in"
    assert "airport check-in" in scenario.opening_line
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
    assert scenario.user_role == "Learner practicing: Hotel check-in"
    assert scenario.opening_line.startswith("Let's practice Hotel check-in.")
