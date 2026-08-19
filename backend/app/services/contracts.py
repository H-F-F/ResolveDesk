from __future__ import annotations

from typing import Protocol

from .domain import RetrievedChunk


class TextEmbedder(Protocol):
    provider_name: str
    model_name: str

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        ...


class ChatCompletionClient(Protocol):
    provider_name: str
    model_name: str

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        ...


class TicketResponder(Protocol):
    provider_name: str
    model_name: str

    def build_answer(self, question: str, chunks: list[RetrievedChunk]) -> str:
        ...

    def build_ticket_summary(self, question: str, reason: str, chunks: list[RetrievedChunk]) -> str:
        ...
