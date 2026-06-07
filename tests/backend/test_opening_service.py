from backend.app.services.llm import FakeLLMClient
from backend.app.services.opening import OpeningLineService
from backend.app.services.scenarios import get_scenario


def test_opening_service_returns_original_without_known_info() -> None:
    scenario = get_scenario("interview")
    assert scenario is not None
    service = OpeningLineService(FakeLLMClient(responses=["should not be called"]))

    opening = service.generate_opening_line(scenario=scenario, known_info_text=None)

    assert opening == scenario.opening_line
    assert service.llm_client.calls == []


def test_opening_service_uses_llm_for_known_info() -> None:
    scenario = get_scenario("interview")
    assert scenario is not None
    service = OpeningLineService(
        FakeLLMClient(
            responses=[
                """
                {
                  "opening_line": "I saw your API platform background. Could you walk me through one project you led?"
                }
                """
            ]
        )
    )

    opening = service.generate_opening_line(
        scenario=scenario,
        known_info_text="Backend engineer focused on API platforms.",
    )

    assert "API platform" in opening
    assert "known info as background context only" in service.llm_client.calls[0][0].content


def test_opening_service_falls_back_on_invalid_llm_json() -> None:
    scenario = get_scenario("interview")
    assert scenario is not None
    service = OpeningLineService(FakeLLMClient(responses=["not json"]))

    opening = service.generate_opening_line(
        scenario=scenario,
        known_info_text="Backend engineer focused on API platforms.",
    )

    assert opening == (
        "I reviewed the background you shared. "
        "Could you walk me through one project that best matches this role?"
    )


def test_opening_service_rejects_chinese_llm_output() -> None:
    scenario = get_scenario("meeting")
    assert scenario is not None
    service = OpeningLineService(FakeLLMClient(responses=['{"opening_line": "我们开始吧。"}']))

    opening = service.generate_opening_line(
        scenario=scenario,
        known_info_text="Weekly project status notes.",
    )

    assert opening == (
        "I reviewed the notes you shared. "
        "Could you start with the latest progress and the biggest risk?"
    )
    assert not any("\u4e00" <= char <= "\u9fff" for char in opening)
