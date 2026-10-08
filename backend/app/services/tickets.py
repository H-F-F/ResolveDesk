from __future__ import annotations

from datetime import datetime

from ..database import Database
from ..schemas import TICKET_STATUSES, TicketRecord
from ..tracing import traceable


class TicketService:
    def __init__(self, database: Database) -> None:
        self.database = database

    @traceable(name="create_ticket")
    def create_ticket(self, user_question: str, reason: str, summary: str) -> TicketRecord:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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
                INSERT INTO tickets
                (ticket_no, user_question, reason, summary, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'open', ?, ?)
                """,
                (ticket_no, user_question, reason, summary, now, now),
            )
            connection.commit()

        return TicketRecord(
            ticket_no=ticket_no,
            user_question=user_question,
            reason=reason,
            summary=summary,
            status="open",
            created_at=now,
            updated_at=now,
        )

    def list_tickets(self) -> list[TicketRecord]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT ticket_no, user_question, reason, summary, status, created_at, updated_at
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
                status=row["status"] or "open",
                created_at=row["created_at"],
                updated_at=row["updated_at"] or "",
            )
            for row in rows
        ]

    def update_status(self, ticket_no: str, status: str) -> TicketRecord | None:
        """流转工单状态，返回更新后的工单；工单不存在时返回 None。"""
        if status not in TICKET_STATUSES:
            raise ValueError(f"非法工单状态：{status}")

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.database.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE tickets
                SET status = ?, updated_at = ?
                WHERE ticket_no = ?
                """,
                (status, now, ticket_no),
            )
            connection.commit()
            if cursor.rowcount == 0:
                return None
            row = connection.execute(
                """
                SELECT ticket_no, user_question, reason, summary, status, created_at, updated_at
                FROM tickets
                WHERE ticket_no = ?
                """,
                (ticket_no,),
            ).fetchone()

        return TicketRecord(
            ticket_no=row["ticket_no"],
            user_question=row["user_question"],
            reason=row["reason"],
            summary=row["summary"],
            status=row["status"] or "open",
            created_at=row["created_at"],
            updated_at=row["updated_at"] or "",
        )

    def count_tickets(self) -> int:
        return self.database.ticket_count()

    def clear_tickets(self) -> int:
        return self.database.clear_tickets()
