from __future__ import annotations

from hashlib import sha1

from backend.app.models import Scenario


class CustomScenarioBuilder:
    def build(self, prompt: str, *, name: str | None = None) -> Scenario:
        normalized = " ".join(prompt.split())
        label = _custom_scenario_label(normalized, name=name)
        digest = sha1(normalized.lower().encode("utf-8")).hexdigest()[:10]
        return Scenario(
            id=f"custom_{digest}",
            name=label,
            ai_role="Conversation partner",
            user_role=f"Learner practicing: {label}",
            opening_line=f"Let's practice {label}. Could you start with what you want to say first?",
            conversation_goals=[
                f"Practice a realistic conversation based on: {_truncate(normalized, 160)}",
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


def build_custom_scenario(prompt: str, *, name: str | None = None) -> Scenario:
    return custom_scenario_builder.build(prompt, name=name)


def _custom_scenario_label(prompt: str, *, name: str | None) -> str:
    if name and name.strip():
        return _truncate(" ".join(name.split()), 80)
    first_line = prompt.splitlines()[0] if prompt.splitlines() else prompt
    first_sentence = first_line
    for marker in [".", "?", "!"]:
        first_sentence = first_sentence.split(marker, 1)[0]
    words = first_sentence.split()
    if not words:
        return "Custom"
    return _truncate(" ".join(words[:8]), 80)


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


custom_scenario_builder = CustomScenarioBuilder()
