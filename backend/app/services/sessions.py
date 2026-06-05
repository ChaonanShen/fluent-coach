from __future__ import annotations

from backend.app.models import Scenario, Session, TurnSpeaker
from backend.app.services.storage import SQLiteLogStore, log_store


class SessionStore:
    def __init__(self, storage: SQLiteLogStore | None = log_store) -> None:
        self._sessions: dict[str, Session] = {}
        self._storage = storage

    def create(self, scenario: Scenario, *, custom_scenario: Scenario | None = None) -> Session:
        session = Session(scenario_id=scenario.id, custom_scenario=custom_scenario)
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

    def clear(self) -> None:
        self._sessions.clear()


session_store = SessionStore()
