from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from ..database import Database
from ..schemas import EvaluationCaseResult, EvaluationReport
from .agent import SupportAgent
from .responder import SupportResponder
from .tickets import TicketService
from .vector_store import VectorStore


@dataclass(frozen=True)
class EvaluationCase:
    case_id: str
    question: str
    expected_mode: Literal["answer", "ticket"]
    expected_source: str | None = None


DEFAULT_EVALUATION_CASES = [
    EvaluationCase(
        case_id="vpn_answer",
        question="VPN 连不上怎么办",
        expected_mode="answer",
        expected_source="vpn_troubleshooting.txt",
    ),
    EvaluationCase(
        case_id="printer_answer",
        question="打印机无法打印怎么处理",
        expected_mode="answer",
        expected_source="printer_failure.txt",
    ),
    EvaluationCase(
        case_id="email_answer",
        question="邮箱提示密码错误怎么处理",
        expected_mode="answer",
        expected_source="email_login_reset.txt",
    ),
    EvaluationCase(
        case_id="git_answer",
        question="Git push 提示权限不足怎么办",
        expected_mode="answer",
        expected_source="git_access_issue.txt",
    ),
    EvaluationCase(
        case_id="escalation_ticket",
        question="VPN 我试过了还是不行，帮我创建工单",
        expected_mode="ticket",
    ),
    EvaluationCase(
        case_id="unknown_ticket",
        question="公司报销系统打不开",
        expected_mode="ticket",
    ),
]


class SupportEvaluator:
    def __init__(
        self,
        vector_store: VectorStore,
        responder: SupportResponder,
        storage_dir: Path,
        top_k: int,
        score_threshold: float,
        lexical_score_threshold: float,
    ) -> None:
        self.vector_store = vector_store
        self.responder = responder
        self.storage_dir = storage_dir
        self.top_k = top_k
        self.score_threshold = score_threshold
        self.lexical_score_threshold = lexical_score_threshold

    def run_default_suite(self) -> EvaluationReport:
        temp_db_path = self.storage_dir / f"evaluation_{uuid4().hex}.db"
        temp_db_path.parent.mkdir(parents=True, exist_ok=True)

        database = Database(temp_db_path)
        database.initialize()
        ticket_service = TicketService(database)
        agent = SupportAgent(
            vector_store=self.vector_store,
            responder=self.responder,
            ticket_service=ticket_service,
            top_k=self.top_k,
            score_threshold=self.score_threshold,
            lexical_score_threshold=self.lexical_score_threshold,
        )

        try:
            results = [self._evaluate_case(agent, case) for case in DEFAULT_EVALUATION_CASES]
        finally:
            try:
                if temp_db_path.exists():
                    temp_db_path.unlink()
            except PermissionError:
                pass

        total_cases = len(results)
        passed_cases = sum(1 for result in results if result.passed)
        failed_cases = total_cases - passed_cases

        return EvaluationReport(
            suite_name="default_sample_suite",
            evaluated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            total_cases=total_cases,
            passed_cases=passed_cases,
            failed_cases=failed_cases,
            pass_rate=round((passed_cases / total_cases) * 100, 2) if total_cases else 0.0,
            results=results,
        )

    def _evaluate_case(self, agent: SupportAgent, case: EvaluationCase) -> EvaluationCaseResult:
        response = agent.chat(case.question)
        actual_source = response.citations[0].source if response.citations else None

        details: list[str] = []
        if response.mode != case.expected_mode:
            details.append(f"期望模式为 {case.expected_mode}，实际为 {response.mode}")

        if case.expected_source and actual_source != case.expected_source:
            details.append(f"期望命中文档为 {case.expected_source}，实际为 {actual_source or '无'}")

        if case.expected_mode == "answer" and not response.citations:
            details.append("回答分支未返回引用来源")

        return EvaluationCaseResult(
            case_id=case.case_id,
            question=case.question,
            expected_mode=case.expected_mode,
            actual_mode=response.mode,
            expected_source=case.expected_source,
            actual_source=actual_source,
            retrieval_score=response.retrieval_score,
            passed=not details,
            details=details,
        )
