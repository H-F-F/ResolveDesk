from __future__ import annotations

import shutil
import unittest
import warnings
from uuid import uuid4
from pathlib import Path

from backend.app.database import Database
from backend.app.services.agent import SupportAgent
from backend.app.services.chunker import TextChunker
from backend.app.services.document_loader import DocumentLoader
from backend.app.services.embedder import LocalHashEmbedder
from backend.app.services.ingestion import IngestionService
from backend.app.services.responder import SupportResponder
from backend.app.services.tickets import TicketService
from backend.app.services.vector_store import VectorStore


ROOT_DIR = Path(__file__).resolve().parents[1]
KNOWLEDGE_BASE_DIR = ROOT_DIR / "data" / "knowledge_base"
TEST_STORAGE_DIR = ROOT_DIR / "storage"

warnings.filterwarnings(
    "ignore",
    category=UserWarning,
    message="Core Pydantic V1 functionality isn't compatible with Python 3.14 or greater.",
)


class AgentFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        TEST_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        run_id = uuid4().hex
        self.db_path = TEST_STORAGE_DIR / f"test_{run_id}.db"
        self.vector_dir = TEST_STORAGE_DIR / f"test_chroma_{run_id}"
        self.vector_dir.mkdir(parents=True, exist_ok=True)

        database = Database(self.db_path)
        database.initialize()

        loader = DocumentLoader()
        chunker = TextChunker(chunk_size=700, overlap=120)
        embedder = LocalHashEmbedder(dimensions=1536)
        vector_store = VectorStore(self.vector_dir, "test_knowledge_base", embedder)
        ingestion_service = IngestionService(loader, chunker, vector_store)
        ingestion_service.ingest_directory(KNOWLEDGE_BASE_DIR)

        self.ticket_service = TicketService(database)
        self.agent = SupportAgent(
            vector_store=vector_store,
            responder=SupportResponder(),
            ticket_service=self.ticket_service,
            top_k=3,
            score_threshold=0.22,
            lexical_score_threshold=0.2,
        )

    def tearDown(self) -> None:
        try:
            if self.db_path.exists():
                self.db_path.unlink()
        except PermissionError:
            pass
        shutil.rmtree(self.vector_dir, ignore_errors=True)

    def test_vpn_question_hits_knowledge_base(self) -> None:
        response = self.agent.chat("VPN 连不上怎么办")

        self.assertEqual(response.mode, "answer")
        self.assertIsNotNone(response.answer)
        self.assertIsNotNone(response.retrieval_score)
        self.assertGreaterEqual(response.retrieval_score or 0.0, 0.22)
        self.assertTrue(response.citations)
        self.assertEqual(response.citations[0].source, "vpn_troubleshooting.txt")

    def test_unknown_question_creates_ticket(self) -> None:
        response = self.agent.chat("公司报销系统打不开")

        self.assertEqual(response.mode, "ticket")
        self.assertIsNotNone(response.ticket)
        self.assertIn("知识库未命中有效结果", response.ticket.reason)

    def test_explicit_escalation_creates_ticket(self) -> None:
        response = self.agent.chat("VPN 我试过了还是不行，帮我创建工单")

        self.assertEqual(response.mode, "ticket")
        self.assertIsNotNone(response.ticket)
        self.assertIn("用户要求升级处理", response.ticket.reason)

    def test_printer_answer_includes_citations(self) -> None:
        response = self.agent.chat("打印机无法打印怎么处理")

        self.assertEqual(response.mode, "answer")
        self.assertTrue(response.citations)
        self.assertEqual(response.citations[0].source, "printer_failure.txt")
        self.assertIn("建议按以下步骤处理", response.answer or "")

    def test_ticket_list_returns_created_ticket(self) -> None:
        response = self.agent.chat("公司报销系统打不开")

        tickets = self.ticket_service.list_tickets()

        self.assertEqual(len(tickets), 1)
        self.assertEqual(tickets[0].ticket_no, response.ticket.ticket_no)
        self.assertEqual(tickets[0].user_question, "公司报销系统打不开")


if __name__ == "__main__":
    unittest.main()
