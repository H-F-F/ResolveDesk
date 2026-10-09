from __future__ import annotations

import json
import shutil
import tempfile
import time
import unittest
import warnings
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from backend.app.config import ROOT_DIR, Settings
from backend.app.main import create_app, stream_events
from backend.app.schemas import ChatRequest
from backend.app.services.agent import SupportAgent
from backend.app.services.contracts import AgentToolCall, AgentToolTurn

KNOWLEDGE_BASE_DIR = ROOT_DIR / "data" / "knowledge_base"

warnings.filterwarnings(
    "ignore",
    category=UserWarning,
    message="Core Pydantic V1 functionality isn't compatible with Python 3.14 or greater.",
)


class StreamingToolClient:
    """模拟支持流式的 LLM：第一轮工具调用，第二轮逐 token 输出答案。"""

    provider_name = "fake-stream"
    model_name = "fake-stream-client"

    def __init__(self) -> None:
        self.turn_count = 0

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        return "工单摘要：用户问题与升级原因。"

    def complete_with_tools_stream(
        self,
        messages: list[dict],
        tools: list[dict],
        on_delta,
    ) -> AgentToolTurn:
        self.turn_count += 1
        # 第一轮：仅工具调用，不产生 content delta
        if self.turn_count == 1:
            return AgentToolTurn(
                content=None,
                tool_calls=[
                    AgentToolCall(
                        call_id="call_search",
                        name="search_knowledge",
                        arguments='{"query": "VPN"}',
                    )
                ],
            )
        # 第二轮：分片推答案
        answer = "根据知识库，建议先检查 VPN 客户端版本。"
        for chunk in (answer[i : i + 5] for i in range(0, len(answer), 5)):
            on_delta(chunk)
        return AgentToolTurn(content=answer, tool_calls=[])

    def complete_with_tools(self, messages: list[dict], tools: list[dict]) -> AgentToolTurn:
        raise AssertionError("流式路径不应调用非流式方法")


class StreamingTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_root = Path(tempfile.mkdtemp(prefix="resolvedesk_test_"))
        run_id = uuid4().hex
        self.storage_dir = self._tmp_root / f"test_stream_{run_id}"
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
            collection_name=f"test_stream_{uuid4().hex}",
            storage_dir=self.storage_dir,
            vector_store_dir=self.vector_store_dir,
            sqlite_path=self.sqlite_path,
            logs_dir=self.logs_dir,
            knowledge_base_dir=KNOWLEDGE_BASE_DIR,
        )
        self.client = TestClient(create_app(self.settings))
        self.client.__enter__()
        self.client.post("/ingest/samples")

    def tearDown(self) -> None:
        self.client.__exit__(None, None, None)
        shutil.rmtree(self._tmp_root, ignore_errors=True)

    def _inject_stream_client(self) -> StreamingToolClient:
        fake = StreamingToolClient()
        services = self.client.app.state.services
        services.agent.responder.chat_client = fake
        return fake

    def test_agent_streams_final_answer_only(self) -> None:
        fake = self._inject_stream_client()
        services = self.client.app.state.services
        agent: SupportAgent = services.agent

        deltas: list[str] = []
        response = agent.chat("VPN 连不上怎么办", on_delta=deltas.append)

        self.assertEqual(response.mode, "answer")
        # 工具轮无 content，delta 只来自最终答案轮
        self.assertEqual("".join(deltas), response.answer)
        self.assertIn("VPN", response.answer)
        self.assertIsNotNone(response.message_id)
        # 决策环执行了工具调用（第一轮）+ 最终轮
        self.assertEqual(fake.turn_count, 2)

    def test_chat_endpoint_streams_sse(self) -> None:
        fake = self._inject_stream_client()
        response = self.client.post(
            "/chat", json={"message": "VPN 连不上怎么办", "stream": True}
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/event-stream", response.headers.get("content-type", ""))
        self.assertEqual(fake.turn_count, 2)

        # 每个分片一个 delta 事件，最后 done 携带完整响应
        delta_contents = [
            json.loads(line[len("data: ") :])["content"]
            for line in response.text.splitlines()
            if '"type": "delta"' in line
        ]
        self.assertGreater(len(delta_contents), 1)
        self.assertEqual("".join(delta_contents), "根据知识库，建议先检查 VPN 客户端版本。")

        done_line = next(line for line in response.text.splitlines() if '"type": "done"' in line)
        payload = json.loads(done_line[len("data: ") :])
        self.assertEqual(payload["response"]["mode"], "answer")
        self.assertIsNotNone(payload["response"]["message_id"])
        self.assertTrue(payload["response"]["citations"])


class SlowStreamClient:
    """模拟慢速流式 LLM：每个 delta 间隔 50ms，共 60 块，用于断连测试。"""

    provider_name = "fake-slow"
    model_name = "fake-slow-client"

    def __init__(self) -> None:
        self.delta_calls = 0
        self.turn_count = 0

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        return "工单摘要"

    def complete_with_tools_stream(self, messages, tools, on_delta) -> AgentToolTurn:
        self.turn_count += 1
        for i in range(60):
            self.delta_calls += 1
            on_delta(f"块{i}。")
            time.sleep(0.05)
        return AgentToolTurn(content="完整答案", tool_calls=[])


class StreamCancellationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_root = Path(tempfile.mkdtemp(prefix="resolvedesk_test_"))
        run_id = uuid4().hex
        self.storage_dir = self._tmp_root / f"test_cancel_{run_id}"
        self.settings = Settings(
            app_env="test",
            chat_provider="offline",
            embedding_provider="offline",
            model_api_base="",
            model_api_key="",
            chat_model_name="",
            embedding_model_name="",
            collection_name=f"test_cancel_{uuid4().hex}",
            storage_dir=self.storage_dir,
            vector_store_dir=self.storage_dir / "chroma",
            sqlite_path=self.storage_dir / "app.db",
            logs_dir=self.storage_dir / "logs",
            knowledge_base_dir=KNOWLEDGE_BASE_DIR,
        )
        self.client = TestClient(create_app(self.settings))
        self.client.__enter__()

    def tearDown(self) -> None:
        self.client.__exit__(None, None, None)
        shutil.rmtree(self._tmp_root, ignore_errors=True)

    def test_client_disconnect_stops_background_thread(self) -> None:
        fake = SlowStreamClient()
        services = self.client.app.state.services
        services.agent.responder.chat_client = fake
        gen = stream_events(services, ChatRequest(message="测试问题", stream=True))

        first = next(gen)  # 拿到首个 delta
        self.assertIn("delta", first)
        time.sleep(0.3)  # 期间后台线程持续推送
        calls_before = fake.delta_calls
        self.assertGreater(calls_before, 3)

        gen.close()  # 模拟客户端断开：生成器关闭触发 cancel
        time.sleep(0.35)

        # 后台线程已停止：delta 调用数不再明显增长
        self.assertLessEqual(fake.delta_calls, calls_before + 1)


if __name__ == "__main__":
    unittest.main()
