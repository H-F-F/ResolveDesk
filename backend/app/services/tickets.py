from __future__ import annotations

from datetime import datetime

from ..database import Database
from ..schemas import TicketRecord
from ..tracing import traceable


class TicketService:
    def __init__(self, database: Database) -> None:
        self.database = database

    @traceable(name="create_ticket")
    def create_ticket(self, user_question: str, reason: str, summary: str) -> TicketRecord:
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        prefix = datetime.now().strftime("IT-%Y%m%d")

        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM tickets WHERE ticket_no LIKE ?",
                (f"{prefix}-%",),
            ).fetchone()
            sequence = int(row["count"]) + 1
            ticket_no = f"{prefix}-{sequence:03d}"

            connection.execute(
                """
                INSERT INTO tickets (ticket_no, user_question, reason, summary, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (ticket_no, user_question, reason, summary, created_at),
            )
            connection.commit()

        return TicketRecord(
            ticket_no=ticket_no,
            user_question=user_question,
            reason=reason,
            summary=summary,
            created_at=created_at,
        )

    def list_tickets(self) -> list[TicketRecord]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT ticket_no, user_question, reason, summary, created_at
                FROM tickets
                ORDER BY id DESC
                """
            ).fetchall()

        return [
            TicketRecord(
                ticket_no=row["ticket_no"],
                user_question=row["user_question"],
                reason=row["reason"],
                summary=row["summary"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def count_tickets(self) -> int:
        return self.database.ticket_count()

    def clear_tickets(self) -> int:
        return self.database.clear_tickets()
