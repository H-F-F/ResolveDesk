from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from .domain import RetrievedChunk


class TextEmbedder(Protocol):
    provider_name: str
    model_name: str

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        ...


@dataclass(frozen=True)
class AgentToolCall:
    """A single tool call requested by the model."""

    call_id: str
    name: str
    arguments: str


@dataclass(frozen=True)
class AgentToolTurn:
    """One model turn that may contain tool calls and/or text content."""

    content: str | None = None
    tool_calls: list[AgentToolCall] = field(default_factory=list)

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)


class ChatCompletionClient(Protocol):
    provider_name: str
    model_name: str

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        ...

    def complete_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
    ) -> AgentToolTurn:
        ...


class TicketResponder(Protocol):
    provider_name: str
    model_name: str

    def build_answer(self, question: str, chunks: list[RetrievedChunk]) -> str:
        ...

    def build_ticket_summary(self, question: str, reason: str, chunks: list[RetrievedChunk]) -> str:
        ...
