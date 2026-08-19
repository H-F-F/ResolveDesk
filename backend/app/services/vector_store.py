from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import chromadb

from .contracts import TextEmbedder
from .domain import ChunkRecord, RetrievedChunk, SourceSummary
from .text_matching import lexical_coverage_score


class VectorStore:
    def __init__(
        self,
        directory: Path,
        collection_name: str,
        embedder: TextEmbedder,
    ) -> None:
        self.client = chromadb.PersistentClient(path=str(directory))
        self.collection_name = collection_name
        self.embedder = embedder
        self.collection = self._get_or_create_collection()

    def count(self) -> int:
        return self.collection.count()

    def upsert_chunks(self, chunks: list[ChunkRecord]) -> None:
        if not chunks:
            return

        by_source: dict[str, list[ChunkRecord]] = defaultdict(list)
        for chunk in chunks:
            by_source[chunk.source].append(chunk)

        for source, source_chunks in by_source.items():
            self._delete_source(source)
            embeddings = self.embedder.embed_texts([chunk.text for chunk in source_chunks])
            self.collection.upsert(
                ids=[chunk.chunk_id for chunk in source_chunks],
                documents=[chunk.text for chunk in source_chunks],
                metadatas=[
                    {
                        "source": chunk.source,
                        "chunk_index": chunk.chunk_index,
                        "snippet": chunk.snippet,
                    }
                    for chunk in source_chunks
                ],
                embeddings=embeddings,
            )

    def search(self, query: str, top_k: int) -> list[RetrievedChunk]:
        document_count = self.count()
        if document_count == 0:
            return []

        query_embedding = self.embedder.embed_texts([query])[0]
        candidate_count = min(document_count, max(top_k * 4, 8))
        result = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=candidate_count,
            include=["documents", "metadatas", "distances"],
        )

        ids = result.get("ids", [[]])[0]
        documents = result.get("documents", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]

        hits: list[RetrievedChunk] = []
        for chunk_id, document, metadata, distance in zip(ids, documents, metadatas, distances):
            dense_score = max(0.0, 1.0 - float(distance))
            lexical_score = lexical_coverage_score(query, document)
            score = (0.45 * dense_score) + (0.55 * lexical_score)
            hits.append(
                RetrievedChunk(
                    chunk_id=chunk_id,
                    source=str(metadata.get("source", "unknown")),
                    text=document,
                    snippet=str(metadata.get("snippet", "")),
                    score=score,
                    dense_score=dense_score,
                    lexical_score=lexical_score,
                )
            )
        hits.sort(key=lambda chunk: chunk.score, reverse=True)
        return hits[:top_k]

    def _delete_source(self, source: str) -> None:
        existing = self.collection.get(where={"source": source})
        ids = existing.get("ids", [])
        if ids:
            self.collection.delete(ids=ids)

    def list_sources(self) -> list[SourceSummary]:
        if self.count() == 0:
            return []

        result = self.collection.get(include=["metadatas"])
        metadatas = result.get("metadatas", [])

        by_source: dict[str, dict[str, int | str]] = {}
        for metadata in metadatas:
            source = str(metadata.get("source", "unknown"))
            entry = by_source.setdefault(
                source,
                {
                    "chunk_count": 0,
                    "snippet": str(metadata.get("snippet", "")),
                },
            )
            entry["chunk_count"] = int(entry["chunk_count"]) + 1
            if not entry["snippet"] and metadata.get("snippet"):
                entry["snippet"] = str(metadata["snippet"])

        summaries = [
            SourceSummary(
                source=source,
                chunk_count=int(payload["chunk_count"]),
                snippet=str(payload["snippet"]),
            )
            for source, payload in by_source.items()
        ]
        summaries.sort(key=lambda item: item.source)
        return summaries

    def reset(self) -> None:
        try:
            self.client.delete_collection(name=self.collection_name)
        except ValueError:
            pass
        self.collection = self._get_or_create_collection()

    def _get_or_create_collection(self):
        return self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )
