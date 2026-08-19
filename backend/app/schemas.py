from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class Citation(BaseModel):
    source: str
    chunk_id: str
    score: float
    snippet: str


class TicketRecord(BaseModel):
    ticket_no: str
    user_question: str
    reason: str
    summary: str
    created_at: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="User input message")


class ChatResponse(BaseModel):
    mode: Literal["answer", "ticket"]
    answer: str | None = None
    citations: list[Citation] = Field(default_factory=list)
    ticket: TicketRecord | None = None
    retrieval_score: float | None = None
    debug: dict[str, Any] = Field(default_factory=dict)


class IngestResponse(BaseModel):
    ingested_files: int
    ingested_chunks: int
    sources: list[str]


class DocumentSummary(BaseModel):
    source: str
    chunk_count: int
    snippet: str


class AppStatus(BaseModel):
    app: str
    environment: str
    vector_documents: int
    ticket_count: int
    evaluation_run_count: int
    chat_provider: str
    chat_model: str
    embedding_provider: str
    embedding_model: str
    pdf_supported: bool


class HealthResponse(BaseModel):
    status: Literal["ok"]
    vector_documents: int
    ticket_count: int


class ResetResponse(BaseModel):
    deleted_tickets: int
    deleted_evaluations: int = 0
    vector_documents: int
    sample_data_loaded: bool = False
    ingested_files: int = 0
    ingested_chunks: int = 0
    sources: list[str] = Field(default_factory=list)


class EvaluationRunSummary(BaseModel):
    run_id: str
    suite_name: str
    evaluated_at: str
    total_cases: int
    passed_cases: int
    failed_cases: int
    pass_rate: float


class EvaluationCaseResult(BaseModel):
    case_id: str
    question: str
    expected_mode: Literal["answer", "ticket"]
    actual_mode: Literal["answer", "ticket"]
    expected_source: str | None = None
    actual_source: str | None = None
    retrieval_score: float | None = None
    passed: bool
    details: list[str] = Field(default_factory=list)


class EvaluationReport(BaseModel):
    run_id: str | None = None
    suite_name: str
    evaluated_at: str
    total_cases: int
    passed_cases: int
    failed_cases: int
    pass_rate: float
    results: list[EvaluationCaseResult] = Field(default_factory=list)
