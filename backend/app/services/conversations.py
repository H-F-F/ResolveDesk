from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from ..database import Database
from ..schemas import SessionSummary
from ..tracing import traceable


@dataclass(frozen=True)
class ConversationMessage:
    role: str
    content: str


class ConversationService:
    """Persists chat sessions and messages, and provides recent history for the agent."""

    def __init__(self, database: Database, history_limit: int = 10) -> None:
        self.database = database
        self.history_limit = history_limit

    @traceable(name="get_or_create_session")
    def get_or_create_session(self, session_id: str | None) -> str:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if session_id:
            with self.database.connect() as connection:
                row = connection.execute(
                    "SELECT session_id FROM conversations WHERE session_id = ?",
                    (session_id,),
                ).fetchone()
            if row is not None:
                return session_id
            with self.database.connect() as connection:
                connection.execute(
                    "INSERT INTO conversations (session_id, created_at, updated_at) VALUES (?, ?, ?)",
                    (session_id, now, now),
                )
                connection.commit()
            return session_id

        new_id = uuid.uuid4().hex
        with self.database.connect() as connection:
            connection.execute(
                "INSERT INTO conversations (session_id, created_at, updated_at) VALUES (?, ?, ?)",
                (new_id, now, now),
            )
            connection.commit()
        return new_id

    @traceable(name="append_message")
    def append_message(self, session_id: str, role: str, content: str) -> None:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO messages (session_id, role, content, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (session_id, role, content, now),
            )
            connection.execute(
                "UPDATE conversations SET updated_at = ? WHERE session_id = ?",
                (now, session_id),
            )
            connection.commit()

    def list_messages(
        self,
        session_id: str,
        limit: int | None = None,
    ) -> list[ConversationMessage]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT role, content FROM messages
                WHERE session_id = ?
                ORDER BY id
                """,
                (session_id,),
            ).fetchall()

        messages = [
            ConversationMessage(role=row["role"], content=row["content"])
            for row in rows
        ]
        effective_limit = self.history_limit if limit is None else limit
        if effective_limit > 0 and len(messages) > effective_limit:
            return messages[-effective_limit:]
        return messages

    def list_sessions(self, limit: int = 20) -> list[SessionSummary]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT c.session_id, c.updated_at, COUNT(m.id) AS message_count
                FROM conversations c
                LEFT JOIN messages m ON m.session_id = c.session_id
                GROUP BY c.session_id
                ORDER BY c.updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [
            SessionSummary(
                session_id=row["session_id"],
                message_count=int(row["message_count"]),
                updated_at=row["updated_at"],
            )
            for row in rows
        ]

    def count_sessions(self) -> int:
        return self.database.session_count()

    def clear_all(self) -> int:
        return self.database.clear_conversations()
