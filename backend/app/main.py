from __future__ import annotations

import json as _json
import logging
import queue as _queue
import threading as _threading
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from .config import Settings, settings
from .database import Database
from .logging_config import configure_logging
from .schemas import (
    AppStatus,
    ChatRequest,
    ChatResponse,
    DocumentDeleteResponse,
    DocumentSummary,
    EvaluationReport,
    EvaluationRunSummary,
    FeedbackRequest,
    HealthResponse,
    IngestResponse,
    ResetResponse,
    SessionSummary,
    TicketRecord,
    TicketUpdateRequest,
)
from .services.agent import SupportAgent
from .services.chunker import TextChunker
from .services.contracts import TextEmbedder
from .services.conversations import ConversationService
from .services.document_loader import DocumentLoader
from .services.evaluation_history import EvaluationHistoryService
from .services.evaluator import SupportEvaluator
from .services.ingestion import IngestionService
from .services.providers import build_embedder, build_responder
from .services.responder import SupportResponder
from .services.tickets import TicketService
from .services.vector_store import VectorStore

logger = logging.getLogger(__name__)

# 单文件上传大小上限（接口层校验，防止超大文件整体读入内存）
MAX_UPLOAD_BYTES = 20 * 1024 * 1024

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
    conversation_service: ConversationService
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
    probe_dimension = len(embedder.embed_texts(["维度探测"])[0])
    if probe_dimension != app_settings.embedding_dimension:
        logger.warning(
            "嵌入模型实际维度(%s)与配置 EMBEDDING_DIMENSION(%s)不一致，已按实际维度使用",
            probe_dimension,
            app_settings.embedding_dimension,
        )
    vector_store = VectorStore(
        app_settings.vector_store_dir,
        f"{app_settings.collection_name}_{probe_dimension}",
        embedder,
        embedding_dimension=probe_dimension,
    )
    ingestion_service = IngestionService(loader, chunker, vector_store)
    ticket_service = TicketService(database)
    conversation_service = ConversationService(database)
    evaluation_history = EvaluationHistoryService(database)
    responder = build_responder(app_settings)
    agent = SupportAgent(
        vector_store=vector_store,
        responder=responder,
        ticket_service=ticket_service,
        conversations=conversation_service,
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
        conversation_service=conversation_service,
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
        session_count=services.conversation_service.count_sessions(),
        evaluation_run_count=services.evaluation_history.count_runs(),
        chat_provider=services.responder.provider_name,
        chat_model=services.responder.model_name,
        embedding_provider=services.embedder.provider_name,
        embedding_model=services.embedder.model_name,
        pdf_supported=services.loader.pdf_supported,
        feedback_positive=services.database.feedback_counts()[0],
        feedback_negative=services.database.feedback_counts()[1],
    )


def build_health(services: AppServices) -> HealthResponse:
    return HealthResponse(
        status="ok",
        vector_documents=services.vector_store.count(),
        ticket_count=services.ticket_service.count_tickets(),
    )


class _StreamCancelled(Exception):
    """客户端断开连接，主动中止流式生成线程。"""


def stream_events(services: AppServices, request: ChatRequest):
    """SSE 事件生成器。

    - 真实模型：Agent 决策环非流式，最终答案逐 token 推送（真流式）
    - 离线模式：分块模拟推送，保证演示环境体验一致
    - 客户端断开时通过 cancel 事件中止后台线程，避免资源泄漏
    """
    events: _queue.Queue[tuple[str, object]] = _queue.Queue()
    cancel = _threading.Event()

    def _raise_if_cancelled() -> None:
        if cancel.is_set():
            raise _StreamCancelled()

    def on_delta(chunk: str) -> None:
        _raise_if_cancelled()
        events.put(("delta", chunk))

    def run() -> None:
        try:
            if services.agent.responder.chat_client is not None:
                final = services.agent.chat(
                    request.message,
                    session_id=request.session_id,
                    on_delta=on_delta,
                )
            else:
                response = services.agent.chat(request.message, session_id=request.session_id)
                if response.mode == "answer" and response.answer:
                    answer = response.answer
                    chunk_size = 8
                    for i in range(0, len(answer), chunk_size):
                        _raise_if_cancelled()
                        events.put(("delta", answer[i : i + chunk_size]))
                        # 离线演示按真实流式节奏逐块下发，模拟打字机效果
                        _threading.Event().wait(0.05)
                final = response
            events.put(("done", final))
        except _StreamCancelled:
            # 客户端已断开，静默结束
            pass
        except Exception as exc:  # 转为 SSE error 事件，避免连接悬挂
            logger.exception("Streaming chat request failed")
            events.put(("error", str(exc)))

    worker = _threading.Thread(target=run, daemon=True)
    worker.start()

    try:
        while True:
            kind, payload = events.get()
            if kind == "delta":
                body = _json.dumps({"type": "delta", "content": payload}, ensure_ascii=False)
                yield f"data: {body}\n\n"
            elif kind == "done":
                body = _json.dumps(
                    {"type": "done", "response": payload.model_dump()},
                    ensure_ascii=False,
                )
                yield f"data: {body}\n\n"
                return
            elif kind == "error":
                body = _json.dumps({"type": "error", "detail": payload}, ensure_ascii=False)
                yield f"data: {body}\n\n"
                return
    finally:
        # 客户端断开（生成器被 close）时通知后台线程停止
        cancel.set()


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
        version="0.3.0",
        description="企业 IT 知识库工单助手：RAG 检索 + Tool Calling Agent + 多轮会话 + 可观测性",
        lifespan=lifespan,
    )
    application.state.services = services

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
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

    @application.delete("/documents/{source}", response_model=DocumentDeleteResponse)
    def delete_document(source: str) -> DocumentDeleteResponse:
        deleted_chunks = services.vector_store.delete_source(source)
        if deleted_chunks == 0:
            raise HTTPException(status_code=404, detail=f"文档不存在：{source}")
        logger.info("Deleted document %s (%s chunks)", source, deleted_chunks)
        return DocumentDeleteResponse(source=source, deleted_chunks=deleted_chunks)

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
        raw_documents = []
        for file in files:
            # 接口层显式校验：白名单与 loader 共用，避免异常文件进入解析流程
            suffix = Path(file.filename or "").suffix.lower()
            if suffix not in services.loader.supported_suffixes:
                raise HTTPException(
                    status_code=400,
                    detail=f"暂不支持的文件类型: {suffix or '(无扩展名)'}",
                )
            content = await file.read()
            if len(content) > MAX_UPLOAD_BYTES:
                raise HTTPException(
                    status_code=400,
                    detail=f"文件 {file.filename} 超过 {MAX_UPLOAD_BYTES // (1024 * 1024)}MB 上限",
                )
            raw_documents.append(services.loader.load_bytes(file.filename, content))
        try:
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
            deleted_sessions = services.conversation_service.clear_all()
            services.vector_store.reset()

            if load_samples:
                result = services.ingestion_service.ingest_directory(runtime_settings.knowledge_base_dir)
                logger.info("Reset application state and reloaded sample documents")
                return ResetResponse(
                    deleted_tickets=deleted_tickets,
                    deleted_evaluations=deleted_evaluations,
                    deleted_sessions=deleted_sessions,
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
                deleted_sessions=deleted_sessions,
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
        if request.stream:
            return StreamingResponse(
                stream_events(services, request),
                media_type="text/event-stream",
            )

        try:
            return services.agent.chat(request.message, session_id=request.session_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            logger.exception("Chat request failed")
            raise HTTPException(status_code=500, detail="问答处理失败") from exc

    @application.patch("/tickets/{ticket_no}", response_model=TicketRecord)
    def update_ticket(ticket_no: str, request: TicketUpdateRequest) -> TicketRecord:
        try:
            ticket = services.ticket_service.update_status(ticket_no, request.status)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if ticket is None:
            raise HTTPException(status_code=404, detail=f"工单不存在：{ticket_no}")
        return ticket

    @application.post("/feedback")
    def feedback(request: FeedbackRequest) -> dict[str, object]:
        updated = services.database.set_message_rating(request.message_id, request.rating)
        if not updated:
            raise HTTPException(status_code=404, detail=f"消息不存在：{request.message_id}")
        positive, negative = services.database.feedback_counts()
        return {
            "status": "ok",
            "feedback_positive": positive,
            "feedback_negative": negative,
        }

    @application.get("/tickets", response_model=list[TicketRecord])
    def list_tickets() -> list[TicketRecord]:
        return services.ticket_service.list_tickets()

    @application.get("/sessions", response_model=list[SessionSummary])
    def list_sessions() -> list[SessionSummary]:
        return services.conversation_service.list_sessions()

    return application


app = create_app()
