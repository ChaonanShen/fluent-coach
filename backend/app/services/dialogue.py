from __future__ import annotations

from functools import lru_cache
from typing import Any

from backend.app.core.fixtures import load_text_fixture
from backend.app.models import Scenario, Session, Turn, TurnSpeaker


@lru_cache(maxsize=1)
def _dialogue_samples() -> tuple[dict[str, Any], ...]:
    payload = load_text_fixture("dialogue_samples")
    return tuple(payload["samples"])


def _normalize(text: str) -> str:
    return " ".join(text.strip().lower().split())


class DialogueReply:
    def __init__(self, text: str, current_goal: str, next_intent: str) -> None:
        self.text = text
        self.current_goal = current_goal
        self.next_intent = next_intent


class DialogueService:
    def generate_reply(
        self,
        *,
        session: Session,
        scenario: Scenario,
        user_text: str,
    ) -> DialogueReply:
        fixture_reply = self._match_fixture_reply(
            scenario_id=scenario.id,
            user_text=user_text,
        )
        current_goal = self._current_goal(scenario, session)
        if fixture_reply is not None:
            return DialogueReply(
                text=fixture_reply,
                current_goal=current_goal,
                next_intent="continue_fixture_dialogue",
            )

        return DialogueReply(
            text=self._fallback_reply(scenario),
            current_goal=current_goal,
            next_intent="ask_for_specific_example",
        )

    def add_text_turns(
        self,
        *,
        session: Session,
        scenario: Scenario,
        user_text: str,
    ) -> tuple[Turn, Turn, DialogueReply]:
        user_turn = session.add_turn(speaker=TurnSpeaker.USER, text=user_text)
        reply = self.generate_reply(session=session, scenario=scenario, user_text=user_text)
        ai_turn = session.add_turn(speaker=TurnSpeaker.AI, text=reply.text)
        return user_turn, ai_turn, reply

    def _match_fixture_reply(self, *, scenario_id: str, user_text: str) -> str | None:
        normalized = _normalize(user_text)
        for sample in _dialogue_samples():
            if sample["scenario_id"] != scenario_id:
                continue
            turns = sample["turns"]
            for index, turn in enumerate(turns[:-1]):
                if turn["speaker"] != "user":
                    continue
                if _normalize(turn["text"]) != normalized:
                    continue
                next_turn = turns[index + 1]
                if next_turn["speaker"] == "ai":
                    return str(next_turn["text"])
        return None

    def _current_goal(self, scenario: Scenario, session: Session) -> str:
        if not scenario.conversation_goals:
            return "continue_conversation"
        user_turn_count = sum(1 for turn in session.turns if turn.speaker == TurnSpeaker.USER)
        index = min(user_turn_count, len(scenario.conversation_goals) - 1)
        return scenario.conversation_goals[index]

    def _fallback_reply(self, scenario: Scenario) -> str:
        if scenario.id == "interview":
            return "Thanks. Could you share one specific example that shows your impact?"
        if scenario.id == "restaurant_ordering":
            return "Got it. Would you like anything to drink with that?"
        if scenario.id == "meeting":
            return "Thanks for the update. What is the main risk we should track next?"
        return "Thanks. Could you tell me a little more?"


dialogue_service = DialogueService()
