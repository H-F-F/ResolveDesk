from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from backend.app.config import Settings
from backend.app.services.domain import RetrievedChunk
from backend.app.services.embedder import LocalHashEmbedder, OpenAICompatibleEmbedder
from backend.app.services.providers import build_embedder, build_responder
from backend.app.services.responder import SupportResponder


class FakeChatClient:
    provider_name = "fake"
    model_name = "fake-model"

    def __init__(self, response: str, *, fail: bool = False) -> None:
        self.response = response
        self.fail = fail

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        if self.fail:
            raise ValueError("boom")
        return self.response


class ModelRuntimeTests(unittest.TestCase):
    def test_build_embedder_returns_offline_embedder_by_default(self) -> None:
        embedder = build_embedder(Settings(embedding_provider="offline"))

        self.assertIsInstance(embedder, LocalHashEmbedder)
        self.assertEqual(embedder.provider_name, "offline")

    def test_build_responder_requires_model_config_for_openai_compatible(self) -> None:
        with self.assertRaises(ValueError) as context:
            build_responder(
                Settings(
                    chat_provider="openai_compatible",
                    model_api_base="",
                    model_api_key="",
                    chat_model_name="",
                )
            )

        self.assertIn("MODEL_API_BASE", str(context.exception))

    def test_openai_compatible_embedder_parses_vectors(self) -> None:
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "data": [
                {"embedding": [0.1, 0.2]},
                {"embedding": [0.3, 0.4]},
            ]
        }

        with patch("backend.app.services.embedder.requests.post", return_value=response) as mock_post:
            embedder = OpenAICompatibleEmbedder(
                base_url="https://example.com/v1",
                api_key="secret",
                model_name="text-embedding",
            )
            vectors = embedder.embed_texts(["hello", "world"])

        self.assertEqual(vectors, [[0.1, 0.2], [0.3, 0.4]])
        self.assertEqual(mock_post.call_count, 1)

    def test_support_responder_uses_chat_client_when_available(self) -> None:
        responder = SupportResponder(chat_client=FakeChatClient("这是模型回答"))
        chunks = [
            RetrievedChunk(
                chunk_id="1",
                source="vpn_troubleshooting.txt",
                text="处理步骤 1. 检查网络 2. 检查 VPN 地址",
                snippet="处理步骤 1. 检查网络",
                score=0.88,
                dense_score=0.9,
                lexical_score=0.86,
            )
        ]

        answer = responder.build_answer("VPN 连不上怎么办", chunks)

        self.assertEqual(answer, "这是模型回答")
        self.assertEqual(responder.provider_name, "fake")

    def test_support_responder_falls_back_to_heuristic_when_llm_fails(self) -> None:
        responder = SupportResponder(chat_client=FakeChatClient("ignored", fail=True))

        answer = responder.build_answer("VPN 连不上怎么办", [])

        self.assertEqual(answer, "知识库中没有找到可用答案。")


if __name__ == "__main__":
    unittest.main()
