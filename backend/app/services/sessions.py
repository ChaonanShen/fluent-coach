from __future__ import annotations

from datetime import datetime

from backend.app.models import KnownInfoSource, Scenario, Session, SessionTitleSource, TurnSpeaker
from backend.app.services.storage import SQLiteLogStore, log_store


class SessionStore:
    def __init__(self, storage: SQLiteLogStore | None = log_store) -> None:
        self._sessions: dict[str, Session] = {}
        self._storage = storage

    def create(
        self,
        scenario: Scenario,
        *,
        custom_scenario: Scenario | None = None,
        custom_prompt: str | None = None,
        known_info_text: str | None = None,
        known_info_sources: list[KnownInfoSource] | None = None,
    ) -> Session:
        session = Session(
            scenario_id=scenario.id,
            custom_scenario=custom_scenario,
            scenario_name_snapshot=scenario.name,
            custom_prompt=custom_prompt,
            known_info_text=known_info_text,
            known_info_sources=known_info_sources or [],
        )
        session.rename(_fallback_title(scenario.name, session.created_at), source=SessionTitleSource.FALLBACK)
        session.add_turn(speaker=TurnSpeaker.AI, text=scenario.opening_line)
        self._sessions[session.id] = session
        if self._storage is not None:
            self._storage.save_session(session)
        return session

    def get(self, session_id: str) -> Session | None:
        session = self._sessions.get(session_id)
        if session is not None:
            return session
        if self._storage is None:
            return None
        session = self._storage.get_session(session_id)
        if session is not None:
            self._sessions[session.id] = session
        return session

    def list(self) -> list[Session]:
        sessions: dict[str, Session] = {}
        if self._storage is not None:
            sessions.update({session.id: session for session in self._storage.list_sessions()})
        sessions.update(self._sessions)
        return sorted(sessions.values(), key=lambda session: session.created_at, reverse=True)

    def end(self, session_id: str) -> Session | None:
        session = self.get(session_id)
        if session is None:
            return None
        if session.ended_at is None:
            session.end()
        if self._storage is not None:
            self._storage.save_session(session)
        return session

    def save(self, session: Session) -> None:
        self._sessions[session.id] = session
        if self._storage is not None:
            self._storage.save_session(session)

    def rename(self, session_id: str, title: str) -> Session | None:
        session = self.get(session_id)
        if session is None:
            return None
        session.rename(title, source=SessionTitleSource.MANUAL)
        self.save(session)
        return session

    def clear(self) -> None:
        self._sessions.clear()


def _fallback_title(scenario_name: str, created_at: datetime) -> str:
    return f"{scenario_name} - {created_at.strftime('%Y-%m-%d %H:%M UTC')}"


session_store = SessionStore()
