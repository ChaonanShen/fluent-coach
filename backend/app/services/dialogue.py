from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache
from typing import Any, Literal

from backend.app.core.fixtures import load_text_fixture
from backend.app.models import Scenario, Session, Turn, TurnSpeaker
from backend.app.services.llm import LLMClient, LLMMessage, StructuredJSONCaller, create_llm_client_from_env
from backend.app.models import AnalysisStage


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


class DialogueStreamReply:
    def __init__(self, chunks: Iterator[str], current_goal: str, next_intent: str) -> None:
        self.chunks = chunks
        self.current_goal = current_goal
        self.next_intent = next_intent


class DialogueService:
    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.llm_client = llm_client

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

        if self.llm_client is not None:
            llm_reply = self._generate_with_llm(
                session=session,
                scenario=scenario,
                user_text=user_text,
                current_goal=current_goal,
            )
            if llm_reply is not None:
                return llm_reply

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
        user_mode: Literal["text", "audio"] = "text",
        user_audio_path: str | None = None,
    ) -> tuple[Turn, Turn, DialogueReply]:
        user_turn = session.add_turn(
            speaker=TurnSpeaker.USER,
            text=user_text,
            mode=user_mode,
            audio_path=user_audio_path,
        )
        reply = self.generate_reply(session=session, scenario=scenario, user_text=user_text)
        ai_turn = session.add_turn(speaker=TurnSpeaker.AI, text=reply.text)
        return user_turn, ai_turn, reply

    def generate_reply_stream(
        self,
        *,
        session: Session,
        scenario: Scenario,
        user_text: str,
    ) -> DialogueStreamReply | None:
        if self._match_fixture_reply(scenario_id=scenario.id, user_text=user_text) is not None:
            return None
        if self.llm_client is None or not hasattr(self.llm_client, "stream_complete"):
            return None
        current_goal = self._current_goal(scenario, session)
        messages = self._streaming_messages(
            session=session,
            scenario=scenario,
            user_text=user_text,
            current_goal=current_goal,
        )
        return DialogueStreamReply(
            chunks=self.llm_client.stream_complete(messages),
            current_goal=current_goal,
            next_intent="continue_conversation",
        )

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

    def _generate_with_llm(
        self,
        *,
        session: Session,
        scenario: Scenario,
        user_text: str,
        current_goal: str,
    ) -> DialogueReply | None:
        caller = StructuredJSONCaller(self.llm_client, stage=AnalysisStage.GRAMMAR)
        history = [
            {"speaker": turn.speaker.value, "text": turn.text}
            for turn in session.turns[-8:]
        ]
        result = caller.call(
            [
                LLMMessage(
                    role="system",
                    content=(
                        "You are the AI role in an English speaking practice scenario. "
                        "Always reply in English, regardless of the language used to describe the scenario. "
                        "Continue the conversation naturally. Do not teach grammar in the reply. "
                        "Return JSON only with keys: reply_text, current_goal, next_intent."
                    ),
                ),
                LLMMessage(
                    role="user",
                    content=(
                        f"scenario_id: {scenario.id}\n"
                        f"ai_role: {scenario.ai_role}\n"
                        f"user_role: {scenario.user_role}\n"
                        f"conversation_goals: {scenario.conversation_goals}\n"
                        f"target_expressions: {scenario.target_expressions}\n"
                        f"current_goal: {current_goal}\n"
                        f"history: {history}\n"
                        f"latest_user_text: {user_text}"
                    ),
                ),
            ]
        )
        if result.data is None:
            return None
        reply_text = str(result.data.get("reply_text") or "").strip()
        if not reply_text:
            return None
        return DialogueReply(
            text=reply_text,
            current_goal=str(result.data.get("current_goal") or current_goal),
            next_intent=str(result.data.get("next_intent") or "continue_conversation"),
        )

    def _streaming_messages(
        self,
        *,
        session: Session,
        scenario: Scenario,
        user_text: str,
        current_goal: str,
    ) -> list[LLMMessage]:
        history = [
            {"speaker": turn.speaker.value, "text": turn.text}
            for turn in session.turns[-8:]
        ]
        return [
            LLMMessage(
                role="system",
                content=(
                    "You are the AI role in an English speaking practice scenario. "
                    "Always reply in English, regardless of the language used to describe the scenario. "
                    "Reply as a natural conversation partner in one or two short sentences. "
                    "Do not teach grammar in this reply. Return plain English text only."
                ),
            ),
            LLMMessage(
                role="user",
                content=(
                    f"scenario_id: {scenario.id}\n"
                    f"ai_role: {scenario.ai_role}\n"
                    f"user_role: {scenario.user_role}\n"
                    f"conversation_goals: {scenario.conversation_goals}\n"
                    f"target_expressions: {scenario.target_expressions}\n"
                    f"current_goal: {current_goal}\n"
                    f"history: {history}\n"
                    f"latest_user_text: {user_text}"
                ),
            ),
        ]


dialogue_service = DialogueService(create_llm_client_from_env())
