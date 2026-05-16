from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


class Database:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS tickets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticket_no TEXT NOT NULL UNIQUE,
                    user_question TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    created_at TEXT NOT NULL
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
                """
            )

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
