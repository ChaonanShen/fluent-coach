from __future__ import annotations

from functools import lru_cache
from hashlib import sha1

from pydantic import TypeAdapter

from backend.app.core.fixtures import load_text_fixture
from backend.app.models import Scenario, Session


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


def make_custom_scenario(topic: str) -> Scenario:
    normalized = " ".join(topic.split())
    digest = sha1(normalized.lower().encode("utf-8")).hexdigest()[:10]
    return Scenario(
        id=f"custom_{digest}",
        name="Custom",
        ai_role="Conversation partner",
        user_role=f"Learner practicing: {normalized}",
        opening_line=f"Let's practice {normalized}. Could you start with what you want to say first?",
        conversation_goals=[
            f"Practice a realistic conversation about {normalized}",
            "Answer naturally and ask one follow-up question when it fits",
        ],
        target_expressions=[
            "Could you tell me more about...",
            "I would like to...",
            "That works for me.",
        ],
        correction_focus=["grammar", "natural expression", "clarity"],
        summary_rubric={
            "grammar": "Use clear sentence structure without repeated major errors.",
            "task": "Keep the custom scenario moving with relevant details.",
        },
    )


def resolve_session_scenario(session: Session) -> Scenario | None:
    return session.custom_scenario or get_scenario(session.scenario_id)
