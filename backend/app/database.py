from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


class Database:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        try:
            # 并发写等待上限：FastAPI 线程池中多个请求同时写库时避免直接报
            # "database is locked"，超过 5 秒仍锁则抛错（显式失败而非静默丢写）
            connection.execute("PRAGMA busy_timeout = 5000")
            yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as connection:
            # WAL：读写不互斥，多线程下并发读 + 单写者，避免锁库
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS tickets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticket_no TEXT NOT NULL UNIQUE,
                    user_question TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'open',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS evaluation_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL UNIQUE,
                    suite_name TEXT NOT NULL,
                    evaluated_at TEXT NOT NULL,
                    total_cases INTEGER NOT NULL,
                    passed_cases INTEGER NOT NULL,
                    failed_cases INTEGER NOT NULL,
                    pass_rate REAL NOT NULL,
                    report_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS conversations (
                    session_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    rating INTEGER,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_messages_session
                ON messages (session_id, id);
                """
            )
            # 兼容旧库：为已存在的表补充新列
            self._ensure_column(connection, "tickets", "status", "TEXT NOT NULL DEFAULT 'open'")
            self._ensure_column(connection, "tickets", "updated_at", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(connection, "messages", "rating", "INTEGER")

    @staticmethod
    def _ensure_column(connection: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        columns = {
            row["name"]
            for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if column not in columns:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
            connection.commit()

    def feedback_counts(self) -> tuple[int, int]:
        """返回 (有用数, 没用数)。"""
        with self.connect() as connection:
            positive = connection.execute(
                "SELECT COUNT(*) AS c FROM messages WHERE rating = 1"
            ).fetchone()["c"]
            negative = connection.execute(
                "SELECT COUNT(*) AS c FROM messages WHERE rating = -1"
            ).fetchone()["c"]
        return int(positive), int(negative)

    def set_message_rating(self, message_id: int, rating: int) -> bool:
        """为消息设置反馈评分（1=有用，-1=没用）。返回是否更新到记录。"""
        with self.connect() as connection:
            cursor = connection.execute(
                "UPDATE messages SET rating = ? WHERE id = ?",
                (rating, message_id),
            )
            connection.commit()
        return cursor.rowcount > 0

    def ticket_count(self) -> int:
        with self.connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM tickets").fetchone()
        return int(row["count"])

    def clear_tickets(self) -> int:
        with self.connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM tickets").fetchone()
            deleted = int(row["count"])
            connection.execute("DELETE FROM tickets")
            connection.commit()
        return deleted

    def evaluation_run_count(self) -> int:
        with self.connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM evaluation_runs").fetchone()
        return int(row["count"])

    def clear_evaluation_runs(self) -> int:
        with self.connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM evaluation_runs").fetchone()
            deleted = int(row["count"])
            connection.execute("DELETE FROM evaluation_runs")
            connection.commit()
        return deleted

    def session_count(self) -> int:
        with self.connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM conversations").fetchone()
        return int(row["count"])

    def clear_conversations(self) -> int:
        with self.connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM conversations").fetchone()
            deleted = int(row["count"])
            connection.execute("DELETE FROM messages")
            connection.execute("DELETE FROM conversations")
            connection.commit()
        return deleted
