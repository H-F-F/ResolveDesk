from __future__ import annotations

import shutil
import tempfile
import unittest
import warnings
from pathlib import Path
from uuid import uuid4

from backend.app.database import Database
from backend.app.services.agent import SupportAgent
from backend.app.services.chunker import TextChunker
from backend.app.services.contracts import AgentToolCall, AgentToolTurn
from backend.app.services.conversations import ConversationService
from backend.app.services.document_loader import DocumentLoader
from backend.app.services.embedder import LocalHashEmbedder
from backend.app.services.ingestion import IngestionService
from backend.app.services.responder import SupportResponder
from backend.app.services.tickets import TicketService
from backend.app.services.vector_store import VectorStore

ROOT_DIR = Path(__file__).resolve().parents[1]
KNOWLEDGE_BASE_DIR = ROOT_DIR / "data" / "knowledge_base"

warnings.filterwarnings(
    "ignore",
    category=UserWarning,
    message="Core Pydantic V1 functionality isn't compatible with Python 3.14 or greater.",
)


class ScriptedToolClient:
    """Emulates an LLM that follows a fixed script of tool-calling turns."""

    provider_name = "fake"
    model_name = "fake-tool-client"

    def __init__(self, script: list[AgentToolTurn]) -> None:
        self.script = list(script)
        self.seen_messages: list[list[dict]] = []

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        return "工单摘要：用户问题与升级原因。"

    def complete_with_tools(self, messages: list[dict], tools: list[dict]) -> AgentToolTurn:
        self.seen_messages.append(list(messages))
        if not self.script:
            raise AssertionError("Client script exhausted")
        return self.script.pop(0)


class ToolCallingAgentTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_root = Path(tempfile.mkdtemp(prefix="resolvedesk_test_"))
        run_id = uuid4().hex
        self.db_path = self._tmp_root / f"test_tool_{run_id}.db"
        self.vector_dir = self._tmp_root / f"test_tool_chroma_{run_id}"
        self.vector_dir.mkdir(parents=True, exist_ok=True)

        database = Database(self.db_path)
        database.initialize()
        loader = DocumentLoader()
        chunker = TextChunker(chunk_size=700, overlap=120)
        embedder = LocalHashEmbedder(dimensions=1536)
        vector_store = VectorStore(self.vector_dir, f"test_tool_{run_id}", embedder)
        IngestionService(loader, chunker, vector_store).ingest_directory(KNOWLEDGE_BASE_DIR)

        self.database = database
        self.ticket_service = TicketService(database)
        self.conversation_service = ConversationService(database)
        self.vector_store = vector_store

    def tearDown(self) -> None:
        shutil.rmtree(self._tmp_root, ignore_errors=True)

    def _build_agent(self, client: ScriptedToolClient) -> SupportAgent:
        return SupportAgent(
            vector_store=self.vector_store,
            responder=SupportResponder(chat_client=client),
            ticket_service=self.ticket_service,
            conversations=self.conversation_service,
            top_k=3,
            score_threshold=0.22,
            lexical_score_threshold=0.2,
        )

    def test_tool_loop_searches_then_answers(self) -> None:
        client = ScriptedToolClient(
            [
                AgentToolTurn(
                    tool_calls=[
                        AgentToolCall(
                            call_id="call_search",
                            name="search_knowledge",
                            arguments='{"query": "VPN 连不上怎么办"}',
                        )
                    ]
                ),
                AgentToolTurn(content="建议检查网络连接，并核对 VPN 服务器地址。"),
            ]
        )
        agent = self._build_agent(client)

        response = agent.chat("VPN 连不上怎么办")

        self.assertEqual(response.mode, "answer")
        self.assertEqual(response.answer, "建议检查网络连接，并核对 VPN 服务器地址。")
        self.assertTrue(response.citations)
        self.assertEqual(response.citations[0].source, "vpn_troubleshooting.txt")
        self.assertEqual(response.debug["decision"], "tool_loop")
        self.assertEqual(response.debug["tools_executed"], ["search_knowledge"])
        self.assertEqual(len(client.seen_messages), 2)

    def test_tool_loop_creates_ticket_on_escalation(self) -> None:
        client = ScriptedToolClient(
            [
                AgentToolTurn(
                    tool_calls=[
                        AgentToolCall(
                            call_id="call_ticket",
                            name="create_ticket",
                            arguments=(
                                '{"question": "VPN 我试过了还是不行，帮我创建工单",'
                                ' "reason": "用户反馈前序方案无效"}'
                            ),
                        )
                    ]
                ),
                AgentToolTurn(content="已为您创建工单。"),
            ]
        )
        agent = self._build_agent(client)

        response = agent.chat("VPN 我试过了还是不行，帮我创建工单")

        self.assertEqual(response.mode, "ticket")
        self.assertIsNotNone(response.ticket)
        self.assertIn("用户反馈前序方案无效", response.ticket.reason)
        self.assertEqual(response.debug["tools_executed"], ["create_ticket"])
        self.assertEqual(len(self.ticket_service.list_tickets()), 1)

    def test_session_history_is_injected_into_second_turn(self) -> None:
        client = ScriptedToolClient(
            [
                AgentToolTurn(content="第一轮回答"),
                AgentToolTurn(content="第二轮回答"),
            ]
        )
        agent = self._build_agent(client)

        first = agent.chat("问题一", session_id="session-abc")
        second = agent.chat("问题二", session_id="session-abc")

        self.assertEqual(first.session_id, "session-abc")
        self.assertEqual(second.session_id, "session-abc")
        second_messages = client.seen_messages[1]
        roles = [message["role"] for message in second_messages]
        self.assertEqual(roles, ["system", "user", "assistant", "user"])
        self.assertEqual(second_messages[1]["content"], "问题一")
        self.assertEqual(second_messages[2]["content"], "第一轮回答")
        self.assertEqual(second_messages[3]["content"], "问题二")
        self.assertEqual(len(self.conversation_service.list_messages("session-abc")), 4)

    def test_messages_are_persisted_per_session(self) -> None:
        client = ScriptedToolClient([AgentToolTurn(content="回答A"), AgentToolTurn(content="回答B")])
        agent = self._build_agent(client)

        agent.chat("问题A", session_id="s1")
        agent.chat("问题B", session_id="s2")

        s1_messages = self.conversation_service.list_messages("s1")
        s2_messages = self.conversation_service.list_messages("s2")
        self.assertEqual([message.content for message in s1_messages], ["问题A", "回答A"])
        self.assertEqual([message.content for message in s2_messages], ["问题B", "回答B"])
        self.assertEqual(self.conversation_service.count_sessions(), 2)


if __name__ == "__main__":
    unittest.main()
