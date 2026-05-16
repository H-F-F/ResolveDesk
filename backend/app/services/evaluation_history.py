from __future__ import annotations

import json
from datetime import datetime

from ..database import Database
from ..schemas import EvaluationReport, EvaluationRunSummary


class EvaluationHistoryService:
    def __init__(self, database: Database) -> None:
        self.database = database

    def save_report(self, report: EvaluationReport) -> EvaluationReport:
        run_date = datetime.now()
        evaluated_at = report.evaluated_at or run_date.strftime("%Y-%m-%d %H:%M:%S")
        prefix = run_date.strftime("EVAL-%Y%m%d")

        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM evaluation_runs WHERE run_id LIKE ?",
                (f"{prefix}-%",),
            ).fetchone()
            sequence = int(row["count"]) + 1
            run_id = f"{prefix}-{sequence:03d}"
            stored_report = report.model_copy(update={"run_id": run_id, "evaluated_at": evaluated_at})

            connection.execute(
                """
                INSERT INTO evaluation_runs (
                    run_id,
                    suite_name,
                    evaluated_at,
                    total_cases,
                    passed_cases,
                    failed_cases,
                    pass_rate,
                    report_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    stored_report.suite_name,
                    stored_report.evaluated_at,
                    stored_report.total_cases,
                    stored_report.passed_cases,
                    stored_report.failed_cases,
                    stored_report.pass_rate,
                    json.dumps(stored_report.model_dump(), ensure_ascii=False),
                ),
            )
            connection.commit()

        return stored_report

    def list_runs(self, limit: int = 20) -> list[EvaluationRunSummary]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT run_id, suite_name, evaluated_at, total_cases, passed_cases, failed_cases, pass_rate
                FROM evaluation_runs
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [
            EvaluationRunSummary(
                run_id=row["run_id"],
                suite_name=row["suite_name"],
                evaluated_at=row["evaluated_at"],
                total_cases=row["total_cases"],
                passed_cases=row["passed_cases"],
                failed_cases=row["failed_cases"],
                pass_rate=row["pass_rate"],
            )
            for row in rows
        ]

    def get_report(self, run_id: str) -> EvaluationReport:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT report_json
                FROM evaluation_runs
                WHERE run_id = ?
                """,
                (run_id,),
            ).fetchone()

        if row is None:
            raise ValueError("评测记录不存在")

        payload = json.loads(row["report_json"])
        return EvaluationReport.model_validate(payload)

    def count_runs(self) -> int:
        return self.database.evaluation_run_count()

    def clear_runs(self) -> int:
        return self.database.clear_evaluation_runs()
