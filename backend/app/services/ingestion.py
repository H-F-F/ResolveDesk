from __future__ import annotations

from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from ..schemas import IngestResponse
from ..tracing import traceable
from .chunker import TextChunker
from .document_loader import DocumentLoader
from .domain import ChunkRecord, RawDocument
from .vector_store import VectorStore


class IngestionService:
    def __init__(
        self,
        loader: DocumentLoader,
        chunker: TextChunker,
        vector_store: VectorStore,
    ) -> None:
        self.loader = loader
        self.chunker = chunker
        self.vector_store = vector_store

    @traceable(name="ingest_raw_documents")
    def ingest_raw_documents(self, documents: list[RawDocument]) -> IngestResponse:
        all_chunks: list[ChunkRecord] = []
        sources: list[str] = []

        for document in documents:
            chunks = self._build_chunks(document)
            all_chunks.extend(chunks)
            sources.append(document.source)

        self.vector_store.upsert_chunks(all_chunks)
        return IngestResponse(
            ingested_files=len(documents),
            ingested_chunks=len(all_chunks),
            sources=sources,
        )

    def ingest_directory(self, directory: Path) -> IngestResponse:
        return self.ingest_raw_documents(self.loader.load_directory(directory))

    def _build_chunks(self, document: RawDocument) -> list[ChunkRecord]:
        chunks: list[ChunkRecord] = []
        for index, chunk_text in enumerate(self.chunker.split(document.text)):
            snippet = chunk_text.replace("\n", " ").strip()[:140]
            chunk_id = str(uuid5(NAMESPACE_URL, f"{document.source}:{index}:{snippet}"))
            chunks.append(
                ChunkRecord(
                    chunk_id=chunk_id,
                    source=document.source,
                    chunk_index=index,
                    text=chunk_text,
                    snippet=snippet,
                )
            )
        return chunks

