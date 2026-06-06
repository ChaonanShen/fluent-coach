from __future__ import annotations

from typing import Protocol

from backend.app.services.llm import LLMClient, LLMMessage
from backend.app.testkit.grammar_injection import next_error_case


class VirtualUser(Protocol):
    def next_clean_turn(
        self,
        *,
        scenario_id: str,
        history: list[dict[str, str]],
        index: int,
    ) -> str:
        """Return the next clean user sentence before error injection."""


class TemplateVirtualUser:
    def next_clean_turn(
        self,
        *,
        scenario_id: str,
        history: list[dict[str, str]],
        index: int,
    ) -> str:
        del history
        return next_error_case(scenario_id, index).clean_text


class LLMVirtualUser:
    def __init__(self, llm_client: LLMClient, fallback: VirtualUser | None = None) -> None:
        self.llm_client = llm_client
        self.fallback = fallback or TemplateVirtualUser()

    def next_clean_turn(
        self,
        *,
        scenario_id: str,
        history: list[dict[str, str]],
        index: int,
    ) -> str:
        prompt = (
            "Generate one natural English learner reply for this speaking practice scenario. "
            "Return one short sentence only, with correct grammar. "
            "Do not include markdown, explanations, or quotation marks.\n"
            f"scenario_id: {scenario_id}\n"
            f"history: {history[-6:]}"
        )
        try:
            text = self.llm_client.complete(
                [
                    LLMMessage(role="system", content="You simulate the learner, not the coach."),
                    LLMMessage(role="user", content=prompt),
                ]
            )
        except Exception:
            return self.fallback.next_clean_turn(scenario_id=scenario_id, history=history, index=index)
        cleaned = " ".join(text.replace("\n", " ").strip().strip("\"'").split())
        if not cleaned or len(cleaned.split()) < 4:
            return self.fallback.next_clean_turn(scenario_id=scenario_id, history=history, index=index)
        return cleaned
