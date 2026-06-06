from __future__ import annotations

from functools import lru_cache

from pydantic import TypeAdapter

from backend.app.core.fixtures import load_text_fixture
from backend.app.models import Scenario, Session
from backend.app.services.custom_scenarios import build_custom_scenario


@lru_cache(maxsize=1)
def list_scenarios() -> tuple[Scenario, ...]:
    payload = load_text_fixture("scenarios")
    scenarios = TypeAdapter(list[Scenario]).validate_python(payload["scenarios"])
    return tuple(scenarios)


def get_scenario(scenario_id: str) -> Scenario | None:
    for scenario in list_scenarios():
        if scenario.id == scenario_id:
            return scenario
    return None


def make_custom_scenario(prompt: str, *, name: str | None = None) -> Scenario:
    return build_custom_scenario(prompt, name=name)


def resolve_session_scenario(session: Session) -> Scenario | None:
    return session.custom_scenario or get_scenario(session.scenario_id)
