from __future__ import annotations

import json
import shutil
import tempfile
import unittest
import warnings
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from backend.app.config import ROOT_DIR, Settings
from backend.app.main import create_app

KNOWLEDGE_BASE_DIR = ROOT_DIR / "data" / "knowledge_base"

warnings.filterwarnings(
    "ignore",
    category=UserWarning,
    message="Core Pydantic V1 functionality isn't compatible with Python 3.14 or greater.",
)


class NewFeatureTests(unittest.TestCase):
    """工单状态流转 / 回答反馈 / 流式输出。"""

    def setUp(self) -> None:
        self._tmp_root = Path(tempfile.mkdtemp(prefix="resolvedesk_test_"))
        run_id = uuid4().hex
        self.storage_dir = self._tmp_root / f"test_api_{run_id}"
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
        # 导入样例知识库，保证库内/库外问题路径可用
        self.client.post("/ingest/samples")

    def tearDown(self) -> None:
        self.client.__exit__(None, None, None)
        shutil.rmtree(self._tmp_root, ignore_errors=True)

    # ------------------------------------------------------------------
    # 工单状态流转
    # ------------------------------------------------------------------

    def test_ticket_status_lifecycle(self) -> None:
        # 库外问题 → 自动建单（status=open）
        response = self.client.post("/chat", json={"message": "公司报销流程是什么"})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["mode"], "ticket")
        ticket_no = body["ticket"]["ticket_no"]
        self.assertEqual(body["ticket"]["status"], "open")

        # 流转：processing → resolved → closed
        for status in ("processing", "resolved", "closed"):
            updated = self.client.patch(f"/tickets/{ticket_no}", json={"status": status})
            self.assertEqual(updated.status_code, 200)
            self.assertEqual(updated.json()["status"], status)

        # 列表校验最终状态
        tickets = self.client.get("/tickets").json()
        match = next(t for t in tickets if t["ticket_no"] == ticket_no)
        self.assertEqual(match["status"], "closed")
        self.assertTrue(match["updated_at"])

    def test_ticket_status_invalid_value(self) -> None:
        response = self.client.post("/chat", json={"message": "怎么买咖啡机"})
        ticket_no = response.json()["ticket"]["ticket_no"]

        bad = self.client.patch(f"/tickets/{ticket_no}", json={"status": "archived"})
        self.assertEqual(bad.status_code, 422)

        missing = self.client.patch("/tickets/IT-NOT-EXIST-999", json={"status": "closed"})
        self.assertEqual(missing.status_code, 404)

    # ------------------------------------------------------------------
    # 回答反馈闭环
    # ------------------------------------------------------------------

    def test_feedback_flow(self) -> None:
        # 库内问题 → answer，响应带 message_id
        response = self.client.post("/chat", json={"message": "VPN 连不上怎么办"})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["mode"], "answer")
        message_id = body["message_id"]
        self.assertIsNotNone(message_id)

        # 初始统计为 0
        status_before = self.client.get("/status").json()
        self.assertEqual(status_before["feedback_positive"], 0)
        self.assertEqual(status_before["feedback_negative"], 0)

        # 有用
        ok = self.client.post("/feedback", json={"message_id": message_id, "rating": 1})
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.json()["feedback_positive"], 1)

        # 没用（同一消息改评，覆盖原评价）
        ok2 = self.client.post("/feedback", json={"message_id": message_id, "rating": -1})
        self.assertEqual(ok2.status_code, 200)
        self.assertEqual(ok2.json()["feedback_negative"], 1)
        self.assertEqual(ok2.json()["feedback_positive"], 0)

        # 状态接口汇总一致
        status_after = self.client.get("/status").json()
        self.assertEqual(status_after["feedback_positive"], 0)
        self.assertEqual(status_after["feedback_negative"], 1)

    def test_feedback_unknown_message(self) -> None:
        response = self.client.post("/feedback", json={"message_id": 999999, "rating": 1})
        self.assertEqual(response.status_code, 404)

    # ------------------------------------------------------------------
    # 流式输出
    # ------------------------------------------------------------------

    def test_chat_stream_returns_sse(self) -> None:
        response = self.client.post(
            "/chat", json={"message": "VPN 连不上怎么办", "stream": True}
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/event-stream", response.headers.get("content-type", ""))

        text = response.text
        self.assertIn('"type": "delta"', text)
        self.assertIn('"type": "done"', text)

        # 校验 done 事件携带完整响应
        done_line = next(line for line in text.splitlines() if '"type": "done"' in line)
        payload = json.loads(done_line[len("data: ") :])
        self.assertEqual(payload["response"]["mode"], "answer")
        self.assertIsNotNone(payload["response"]["message_id"])
        self.assertTrue(payload["response"]["citations"])

    def test_delete_document_by_source(self) -> None:
        docs = self.client.get("/documents").json()
        self.assertGreater(len(docs), 0)
        target = docs[0]["source"]
        count_before = self.client.get("/status").json()["vector_documents"]

        deleted = self.client.delete(f"/documents/{target}")
        self.assertEqual(deleted.status_code, 200)
        body = deleted.json()
        self.assertEqual(body["source"], target)
        self.assertGreater(body["deleted_chunks"], 0)

        # 列表与统计同步
        remaining = self.client.get("/documents").json()
        self.assertNotIn(target, [d["source"] for d in remaining])
        count_after = self.client.get("/status").json()["vector_documents"]
        self.assertEqual(count_after, count_before - body["deleted_chunks"])

        # 删除不存在的文档 → 404
        missing = self.client.delete(f"/documents/{target}")
        self.assertEqual(missing.status_code, 404)

    def test_chat_stream_ticket_mode_is_not_streamed(self) -> None:
        # 转单模式没有长文本，直接返回 JSON
        response = self.client.post(
            "/chat", json={"message": "公司报销流程是什么", "stream": True}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("content-type", "").split(";")[0], "application/json")
        self.assertEqual(response.json()["mode"], "ticket")


if __name__ == "__main__":
    unittest.main()
