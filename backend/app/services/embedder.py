from __future__ import annotations

import hashlib
import logging
import math
from typing import Any

import requests

from ..tracing import traceable
from .text_matching import token_weight, tokenize_text


logger = logging.getLogger(__name__)


class LocalHashEmbedder:
    """A deterministic offline embedder for demo environments."""

    provider_name = "offline"
    model_name = "local-hash"

    def __init__(self, dimensions: int = 1536) -> None:
        self.dimensions = dimensions

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_single(text) for text in texts]

    def _embed_single(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in self._tokenize(text):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:8], "big") % self.dimensions
            sign = 1.0 if digest[8] % 2 == 0 else -1.0
            vector[index] += sign * token_weight(token)

        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]

    def _tokenize(self, text: str) -> list[str]:
        return tokenize_text(text) or ["empty"]


class OpenAICompatibleEmbedder:
    provider_name = "openai_compatible"

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model_name: str,
        *,
        timeout_seconds: float = 60.0,
        verify_ssl: bool = True,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model_name = model_name
        self.timeout_seconds = timeout_seconds
        self.verify_ssl = verify_ssl

    @traceable(name="embed_texts_openai_compatible")
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        response = requests.post(
            f"{self.base_url}/embeddings",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model_name,
                "input": texts,
            },
            timeout=self.timeout_seconds,
            verify=self.verify_ssl,
        )
        self._raise_for_status(response)

        payload = response.json()
        data = payload.get("data", [])
        if not isinstance(data, list) or len(data) != len(texts):
            raise ValueError("Embedding 接口返回结果数量异常")

        vectors: list[list[float]] = []
        for item in data:
            embedding = item.get("embedding")
            if not isinstance(embedding, list):
                raise ValueError("Embedding 接口返回格式异常")
            vectors.append([float(value) for value in embedding])
        return vectors

    def _raise_for_status(self, response: requests.Response) -> None:
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            logger.exception("Embedding request failed with status %s", response.status_code)
            detail = self._extract_error_detail(response)
            raise ValueError(f"Embedding 接口调用失败: {detail}") from exc

    def _extract_error_detail(self, response: requests.Response) -> str:
        try:
            payload: Any = response.json()
        except ValueError:
            payload = None

        if isinstance(payload, dict):
            if isinstance(payload.get("error"), dict) and payload["error"].get("message"):
                return str(payload["error"]["message"])
            if payload.get("message"):
                return str(payload["message"])
        return response.text[:200] or f"HTTP {response.status_code}"
