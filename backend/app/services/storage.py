from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from backend.app.models import (
    AnalysisError,
    GrammarCorrection,
    MistakeItem,
    MistakeType,
    PronunciationAssessment,
    Session,
    Turn,
)


DEFAULT_DB_PATH = Path(os.environ.get("APP_DB_PATH", ".local/speaking_coach.sqlite"))


class SQLiteLogStore:
    def __init__(self, path: Path = DEFAULT_DB_PATH) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    scenario_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    ended_at TEXT,
                    payload TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS turns (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    speaker TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS grammar_corrections (
                    id TEXT PRIMARY KEY,
                    scenario_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS pronunciation_assessments (
                    id TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS mistake_items (
                    id TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    session_id TEXT,
                    turn_id TEXT,
                    source_stage TEXT,
                    subtype TEXT,
                    created_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS analysis_errors (
                    id TEXT PRIMARY KEY,
                    stage TEXT NOT NULL,
                    code TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                """
            )
            _ensure_column(connection, "mistake_items", "session_id", "TEXT")
            _ensure_column(connection, "mistake_items", "turn_id", "TEXT")
            _ensure_column(connection, "mistake_items", "source_stage", "TEXT")
            _ensure_column(connection, "mistake_items", "subtype", "TEXT")

    def save_session(self, session: Session) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO sessions (id, scenario_id, status, created_at, ended_at, payload)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    scenario_id = excluded.scenario_id,
                    status = excluded.status,
                    ended_at = excluded.ended_at,
                    payload = excluded.payload
                """,
                (
                    session.id,
                    session.scenario_id,
                    session.status.value,
                    session.created_at.isoformat(),
                    session.ended_at.isoformat() if session.ended_at else None,
                    _dump_model(session),
                ),
            )
            self._save_turns(connection, session.turns)

    def get_session(self, session_id: str) -> Session | None:
        row = self._fetch_one("SELECT payload FROM sessions WHERE id = ?", (session_id,))
        if row is None:
            return None
        return Session.model_validate(json.loads(row["payload"]))

    def list_sessions(self) -> list[Session]:
        rows = self._fetch_all("SELECT payload FROM sessions ORDER BY created_at DESC", ())
        return [Session.model_validate(json.loads(row["payload"])) for row in rows]

    def save_turn(self, turn: Turn) -> None:
        with self._connect() as connection:
            self._save_turns(connection, [turn])

    def list_turns(self, session_id: str) -> list[Turn]:
        rows = self._fetch_all(
            "SELECT payload FROM turns WHERE session_id = ? ORDER BY created_at ASC",
            (session_id,),
        )
        return [Turn.model_validate(json.loads(row["payload"])) for row in rows]

    def save_grammar_correction(self, correction: GrammarCorrection) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO grammar_corrections (id, scenario_id, created_at, payload)
                VALUES (?, ?, ?, ?)
                """,
                (
                    correction.id,
                    correction.scenario_id,
                    correction.created_at.isoformat(),
                    _dump_model(correction),
                ),
            )

    def save_pronunciation_assessment(self, assessment: PronunciationAssessment) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO pronunciation_assessments (id, provider, created_at, payload)
                VALUES (?, ?, ?, ?)
                """,
                (
                    assessment.id,
                    assessment.provider,
                    assessment.created_at.isoformat(),
                    _dump_model(assessment),
                ),
            )

    def save_mistake_item(self, mistake: MistakeItem) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO mistake_items (
                    id,
                    type,
                    session_id,
                    turn_id,
                    source_stage,
                    subtype,
                    created_at,
                    payload
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    mistake.id,
                    mistake.type.value,
                    mistake.session_id,
                    mistake.turn_id,
                    mistake.source_stage.value if mistake.source_stage else None,
                    mistake.subtype,
                    mistake.created_at.isoformat(),
                    _dump_model(mistake),
                ),
            )

    def list_mistake_items(
        self,
        *,
        session_id: str | None = None,
        mistake_type: MistakeType | None = None,
        subtype: str | None = None,
    ) -> list[MistakeItem]:
        clauses: list[str] = []
        params: list[Any] = []
        if session_id is not None:
            clauses.append("session_id = ?")
            params.append(session_id)
        if mistake_type is not None:
            clauses.append("type = ?")
            params.append(mistake_type.value)
        if subtype is not None:
            clauses.append("subtype = ?")
            params.append(subtype)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._fetch_all(
            f"SELECT payload FROM mistake_items{where} ORDER BY created_at DESC",
            tuple(params),
        )
        return [MistakeItem.model_validate(json.loads(row["payload"])) for row in rows]

    def get_mistake_item(self, mistake_id: str) -> MistakeItem | None:
        row = self._fetch_one("SELECT payload FROM mistake_items WHERE id = ?", (mistake_id,))
        if row is None:
            return None
        return MistakeItem.model_validate(json.loads(row["payload"]))

    def delete_mistake_item(self, mistake_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM mistake_items WHERE id = ?", (mistake_id,))
            return cursor.rowcount > 0

    def delete_mistake_items_for_session(self, session_id: str) -> int:
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM mistake_items WHERE session_id = ?", (session_id,))
            return int(cursor.rowcount)

    def delete_mistake_items_for_sessions(self, session_ids: list[str]) -> int:
        if not session_ids:
            return 0
        placeholders = ", ".join("?" for _ in session_ids)
        with self._connect() as connection:
            cursor = connection.execute(
                f"DELETE FROM mistake_items WHERE session_id IN ({placeholders})",
                tuple(session_ids),
            )
            return int(cursor.rowcount)

    def save_analysis_error(self, error: AnalysisError) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO analysis_errors (id, stage, code, created_at, payload)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    error.id,
                    error.stage.value,
                    error.code,
                    error.created_at.isoformat(),
                    _dump_model(error),
                ),
            )

    def count_rows(self, table: str) -> int:
        allowed = {
            "sessions",
            "turns",
            "grammar_corrections",
            "pronunciation_assessments",
            "mistake_items",
            "analysis_errors",
        }
        if table not in allowed:
            raise ValueError(f"Unsupported table: {table}")
        row = self._fetch_one(f"SELECT COUNT(*) AS count FROM {table}", ())
        return int(row["count"]) if row is not None else 0

    def clear_all(self) -> None:
        with self._connect() as connection:
            for table in [
                "analysis_errors",
                "mistake_items",
                "pronunciation_assessments",
                "grammar_corrections",
                "turns",
                "sessions",
            ]:
                connection.execute(f"DELETE FROM {table}")

    def _save_turns(self, connection: sqlite3.Connection, turns: Iterable[Turn]) -> None:
        connection.executemany(
            """
            INSERT OR REPLACE INTO turns (id, session_id, speaker, created_at, payload)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (
                    turn.id,
                    turn.session_id,
                    turn.speaker.value,
                    turn.created_at.isoformat(),
                    _dump_model(turn),
                )
                for turn in turns
            ],
        )

    def _fetch_one(self, query: str, params: tuple[Any, ...]) -> sqlite3.Row | None:
        with self._connect() as connection:
            return connection.execute(query, params).fetchone()

    def _fetch_all(self, query: str, params: tuple[Any, ...]) -> list[sqlite3.Row]:
        with self._connect() as connection:
            return list(connection.execute(query, params).fetchall())


def _dump_model(model: object) -> str:
    return json.dumps(model.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":"))


def _ensure_column(connection: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    existing = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}
    if column in existing:
        return
    connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


log_store = SQLiteLogStore()
