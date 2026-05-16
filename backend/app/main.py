from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .config import Settings, settings
from .database import Database
from .logging_config import configure_logging
from .schemas import (
    AppStatus,
    ChatRequest,
    ChatResponse,
    DocumentSummary,
    EvaluationReport,
    EvaluationRunSummary,
    HealthResponse,
    IngestResponse,
    ResetResponse,
    TicketRecord,
)
from .services.agent import SupportAgent
from .services.chunker import TextChunker
from .services.contracts import TextEmbedder
from .services.document_loader import DocumentLoader
from .services.evaluator import SupportEvaluator
from .services.evaluation_history import EvaluationHistoryService
from .services.ingestion import IngestionService
from .services.providers import build_embedder, build_responder
from .services.responder import SupportResponder
from .services.tickets import TicketService
from .services.vector_store import VectorStore


logger = logging.getLogger(__name__)

@dataclass
class AppServices:
    settings: Settings
    database: Database
    loader: DocumentLoader
    chunker: TextChunker
    embedder: TextEmbedder
    vector_store: VectorStore
    ingestion_service: IngestionService
    ticket_service: TicketService
    responder: SupportResponder
    agent: SupportAgent
    evaluator: SupportEvaluator
    evaluation_history: EvaluationHistoryService


def build_services(app_settings: Settings) -> AppServices:
    configure_logging(app_settings)
    app_settings.ensure_directories()

    database = Database(app_settings.sqlite_path)
    database.initialize()
    loader = DocumentLoader()
    chunker = TextChunker(app_settings.chunk_size, app_settings.chunk_overlap)
    embedder = build_embedder(app_settings)
    vector_store = VectorStore(
        app_settings.vector_store_dir,
        f"{app_settings.collection_name}_{app_settings.embedding_dimension}",
        embedder,
    )
    ingestion_service = IngestionService(loader, chunker, vector_store)
    ticket_service = TicketService(database)
    evaluation_history = EvaluationHistoryService(database)
    responder = build_responder(app_settings)
    agent = SupportAgent(
        vector_store=vector_store,
        responder=responder,
        ticket_service=ticket_service,
        top_k=app_settings.rag_top_k,
        score_threshold=app_settings.rag_score_threshold,
        lexical_score_threshold=app_settings.rag_lexical_score_threshold,
    )
    evaluator = SupportEvaluator(
        vector_store=vector_store,
        responder=responder,
        storage_dir=app_settings.storage_dir,
        top_k=app_settings.rag_top_k,
        score_threshold=app_settings.rag_score_threshold,
        lexical_score_threshold=app_settings.rag_lexical_score_threshold,
    )
    return AppServices(
        settings=app_settings,
        database=database,
        loader=loader,
        chunker=chunker,
        embedder=embedder,
        vector_store=vector_store,
        ingestion_service=ingestion_service,
        ticket_service=ticket_service,
        responder=responder,
        agent=agent,
        evaluator=evaluator,
        evaluation_history=evaluation_history,
    )


def build_status(services: AppServices) -> AppStatus:
    return AppStatus(
        app=services.settings.app_name,
        environment=services.settings.app_env,
        vector_documents=services.vector_store.count(),
        ticket_count=services.ticket_service.count_tickets(),
        evaluation_run_count=services.evaluation_history.count_runs(),
        chat_provider=services.responder.provider_name,
        chat_model=services.responder.model_name,
        embedding_provider=services.embedder.provider_name,
        embedding_model=services.embedder.model_name,
        pdf_supported=services.loader.pdf_supported,
    )


def build_health(services: AppServices) -> HealthResponse:
    return HealthResponse(
        status="ok",
        vector_documents=services.vector_store.count(),
        ticket_count=services.ticket_service.count_tickets(),
    )


def create_app(app_settings: Settings | None = None) -> FastAPI:
    runtime_settings = app_settings or settings
    services = build_services(runtime_settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        logger.info(
            "Application started | chat=%s/%s | embedding=%s/%s",
            services.responder.provider_name,
            services.responder.model_name,
            services.embedder.provider_name,
            services.embedder.model_name,
        )
        yield

    application = FastAPI(
        title=runtime_settings.app_name,
        version="0.2.0",
        description="面试版 Agent + RAG 企业 IT 知识库工单助手",
        lifespan=lifespan,
    )
    application.state.services = services

    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @application.get("/", response_model=AppStatus)
    def root() -> AppStatus:
        return build_status(services)

    @application.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return build_health(services)

    @application.get("/status", response_model=AppStatus)
    def status() -> AppStatus:
        return build_status(services)

    @application.get("/documents", response_model=list[DocumentSummary])
    def list_documents() -> list[DocumentSummary]:
        return [
            DocumentSummary(
                source=item.source,
                chunk_count=item.chunk_count,
                snippet=item.snippet,
            )
            for item in services.vector_store.list_sources()
        ]

    @application.get("/evaluations", response_model=list[EvaluationRunSummary])
    def list_evaluations() -> list[EvaluationRunSummary]:
        return services.evaluation_history.list_runs()

    @application.get("/evaluations/{run_id}", response_model=EvaluationReport)
    def get_evaluation(run_id: str) -> EvaluationReport:
        try:
            return services.evaluation_history.get_report(run_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @application.post("/ingest", response_model=IngestResponse)
    async def ingest_documents(files: list[UploadFile] = File(...)) -> IngestResponse:
        try:
            raw_documents = []
            for file in files:
                content = await file.read()
                raw_documents.append(services.loader.load_bytes(file.filename, content))
            result = services.ingestion_service.ingest_raw_documents(raw_documents)
            logger.info("Ingested %s files and %s chunks", result.ingested_files, result.ingested_chunks)
            return result
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            logger.exception("Failed to ingest uploaded documents")
            raise HTTPException(status_code=500, detail="文档导入失败") from exc

    @application.post("/ingest/samples", response_model=IngestResponse)
    def ingest_samples() -> IngestResponse:
        try:
            result = services.ingestion_service.ingest_directory(runtime_settings.knowledge_base_dir)
            logger.info("Loaded sample documents: %s", ", ".join(result.sources))
            return result
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            logger.exception("Failed to ingest sample documents")
            raise HTTPException(status_code=500, detail="示例知识库导入失败") from exc

    @application.post("/reset", response_model=ResetResponse)
    def reset(load_samples: bool = False, clear_evaluations: bool = False) -> ResetResponse:
        try:
            deleted_tickets = services.ticket_service.clear_tickets()
            deleted_evaluations = services.evaluation_history.clear_runs() if clear_evaluations else 0
            services.vector_store.reset()

            if load_samples:
                result = services.ingestion_service.ingest_directory(runtime_settings.knowledge_base_dir)
                logger.info("Reset application state and reloaded sample documents")
                return ResetResponse(
                    deleted_tickets=deleted_tickets,
                    deleted_evaluations=deleted_evaluations,
                    vector_documents=services.vector_store.count(),
                    sample_data_loaded=True,
                    ingested_files=result.ingested_files,
                    ingested_chunks=result.ingested_chunks,
                    sources=result.sources,
                )

            logger.info("Reset application state")
            return ResetResponse(
                deleted_tickets=deleted_tickets,
                deleted_evaluations=deleted_evaluations,
                vector_documents=services.vector_store.count(),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            logger.exception("Failed to reset application state")
            raise HTTPException(status_code=500, detail="重置项目状态失败") from exc

    @application.post("/evaluate/samples", response_model=EvaluationReport)
    def evaluate_samples() -> EvaluationReport:
        try:
            report = services.evaluator.run_default_suite()
            report = services.evaluation_history.save_report(report)
            logger.info(
                "Completed evaluation suite %s: %s/%s passed",
                report.run_id,
                report.passed_cases,
                report.total_cases,
            )
            return report
        except Exception as exc:
            logger.exception("Failed to run evaluation suite")
            raise HTTPException(status_code=500, detail="运行内置评测失败") from exc

    @application.post("/chat", response_model=ChatResponse)
    def chat(request: ChatRequest) -> ChatResponse:
        try:
            return services.agent.chat(request.message)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            logger.exception("Chat request failed")
            raise HTTPException(status_code=500, detail="问答处理失败") from exc

    @application.get("/tickets", response_model=list[TicketRecord])
    def list_tickets() -> list[TicketRecord]:
        return services.ticket_service.list_tickets()

    return application


app = create_app()
