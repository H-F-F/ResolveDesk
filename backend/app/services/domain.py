from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RawDocument:
    source: str
    text: str


@dataclass(frozen=True)
class ChunkRecord:
    chunk_id: str
    source: str
    chunk_index: int
    text: str
    snippet: str


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: str
    source: str
    text: str
    snippet: str
    score: float
    dense_score: float
    lexical_score: float


@dataclass(frozen=True)
class SourceSummary:
    source: str
    chunk_count: int
    snippet: str
