from __future__ import annotations

import shutil
import unittest
import warnings
from uuid import uuid4

from fastapi.testclient import TestClient

from backend.app.config import ROOT_DIR, Settings
from backend.app.main import create_app


KNOWLEDGE_BASE_DIR = ROOT_DIR / "data" / "knowledge_base"
TEST_STORAGE_DIR = ROOT_DIR / "storage"

warnings.filterwarnings(
    "ignore",
    category=UserWarning,
    message="Core Pydantic V1 functionality isn't compatible with Python 3.14 or greater.",
)


class ApiFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        TEST_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        run_id = uuid4().hex
        self.storage_dir = TEST_STORAGE_DIR / f"test_api_{run_id}"
        self.vector_store_dir = self.storage_dir / "chroma"
        self.sqlite_path = self.storage_dir / "app.db"
        self.logs_dir = self.storage_dir / "logs"

        self.settings = Settings(
            app_env="test",
            chat_provider="offline",
            embedding_provider="offline",
            model_api_base="",
            model_api_key="",
            chat_model_name="",
            embedding_model_name="",
            collection_name=f"test_api_{uuid4().hex}",
            storage_dir=self.storage_dir,
            vector_store_dir=self.vector_store_dir,
            sqlite_path=self.sqlite_path,
            logs_dir=self.logs_dir,
            knowledge_base_dir=KNOWLEDGE_BASE_DIR,
        )
        self.client = TestClient(create_app(self.settings))
        self.client.__enter__()

    def tearDown(self) -> None:
        self.client.__exit__(None, None, None)
        try:
            if self.sqlite_path.exists():
                self.sqlite_path.unlink()
        except PermissionError:
            pass
        shutil.rmtree(self.storage_dir, ignore_errors=True)

    def test_status_reflects_sample_ingestion(self) -> None:
        response = self.client.get("/status")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["vector_documents"], 0)
        self.assertEqual(response.json()["ticket_count"], 0)
        self.assertEqual(response.json()["evaluation_run_count"], 0)
        self.assertEqual(response.json()["chat_provider"], "offline")
        self.assertEqual(response.json()["embedding_provider"], "offline")

        ingest_response = self.client.post("/ingest/samples")
        self.assertEqual(ingest_response.status_code, 200)
        self.assertEqual(ingest_response.json()["ingested_files"], 5)

        status_response = self.client.get("/status")
        self.assertEqual(status_response.status_code, 200)
        self.assertEqual(status_response.json()["vector_documents"], 5)
        self.assertEqual(status_response.json()["ticket_count"], 0)
        self.assertEqual(status_response.json()["evaluation_run_count"], 0)
        self.assertEqual(status_response.json()["chat_model"], "heuristic-responder")
        self.assertEqual(status_response.json()["embedding_model"], "local-hash")

    def test_documents_endpoint_lists_loaded_sources(self) -> None:
        self.client.post("/ingest/samples")

        response = self.client.get("/documents")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload), 5)
        self.assertEqual(payload[0]["source"], "email_login_reset.txt")
        self.assertGreaterEqual(payload[0]["chunk_count"], 1)
        self.assertTrue(payload[0]["snippet"])

    def test_reset_clears_vector_store_and_tickets(self) -> None:
        self.client.post("/ingest/samples")

        answer_response = self.client.post("/chat", json={"message": "VPN 连不上怎么办"})
        self.assertEqual(answer_response.status_code, 200)
        self.assertEqual(answer_response.json()["mode"], "answer")

        ticket_response = self.client.post("/chat", json={"message": "公司报销系统打不开"})
        self.assertEqual(ticket_response.status_code, 200)
        self.assertEqual(ticket_response.json()["mode"], "ticket")

        tickets_response = self.client.get("/tickets")
        self.assertEqual(tickets_response.status_code, 200)
        self.assertEqual(len(tickets_response.json()), 1)

        reset_response = self.client.post("/reset")
        self.assertEqual(reset_response.status_code, 200)
        self.assertEqual(reset_response.json()["deleted_tickets"], 1)
        self.assertEqual(reset_response.json()["vector_documents"], 0)

        status_response = self.client.get("/status")
        self.assertEqual(status_response.status_code, 200)
        self.assertEqual(status_response.json()["vector_documents"], 0)
        self.assertEqual(status_response.json()["ticket_count"], 0)
        self.assertEqual(status_response.json()["evaluation_run_count"], 0)

    def test_evaluation_suite_passes_on_sample_knowledge_base(self) -> None:
        self.client.post("/ingest/samples")

        response = self.client.post("/evaluate/samples")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["suite_name"], "default_sample_suite")
        self.assertEqual(payload["total_cases"], 6)
        self.assertEqual(payload["failed_cases"], 0)
        self.assertEqual(payload["passed_cases"], 6)
        self.assertEqual(payload["pass_rate"], 100.0)
        self.assertTrue(payload["run_id"])

    def test_evaluation_history_is_persisted_and_can_be_reloaded(self) -> None:
        self.client.post("/ingest/samples")

        report = self.client.post("/evaluate/samples").json()
        run_id = report["run_id"]

        history_response = self.client.get("/evaluations")
        self.assertEqual(history_response.status_code, 200)
        history_payload = history_response.json()
        self.assertEqual(len(history_payload), 1)
        self.assertEqual(history_payload[0]["run_id"], run_id)
        self.assertEqual(history_payload[0]["pass_rate"], 100.0)

        detail_response = self.client.get(f"/evaluations/{run_id}")
        self.assertEqual(detail_response.status_code, 200)
        detail_payload = detail_response.json()
        self.assertEqual(detail_payload["run_id"], run_id)
        self.assertEqual(detail_payload["total_cases"], 6)
        self.assertEqual(len(detail_payload["results"]), 6)

        status_response = self.client.get("/status")
        self.assertEqual(status_response.status_code, 200)
        self.assertEqual(status_response.json()["evaluation_run_count"], 1)

    def test_reset_can_clear_evaluation_history(self) -> None:
        self.client.post("/ingest/samples")
        self.client.post("/evaluate/samples")

        reset_response = self.client.post("/reset?clear_evaluations=true")
        self.assertEqual(reset_response.status_code, 200)
        self.assertEqual(reset_response.json()["deleted_evaluations"], 1)

        history_response = self.client.get("/evaluations")
        self.assertEqual(history_response.status_code, 200)
        self.assertEqual(history_response.json(), [])


if __name__ == "__main__":
    unittest.main()
