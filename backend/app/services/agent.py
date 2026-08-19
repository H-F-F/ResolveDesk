from __future__ import annotations

from ..schemas import ChatResponse, Citation
from ..tracing import traceable
from .responder import SupportResponder
from .tickets import TicketService
from .vector_store import VectorStore


ESCALATION_PHRASES = [
    "试过了不行",
    "试过了还是不行",
    "还是不行",
    "没解决",
    "无法处理",
    "创建工单",
    "帮我建工单",
    "转人工",
    "升级处理",
]


class SupportAgent:
    def __init__(
        self,
        vector_store: VectorStore,
        responder: SupportResponder,
        ticket_service: TicketService,
        top_k: int,
        score_threshold: float,
        lexical_score_threshold: float,
    ) -> None:
        self.vector_store = vector_store
        self.responder = responder
        self.ticket_service = ticket_service
        self.top_k = top_k
        self.score_threshold = score_threshold
        self.lexical_score_threshold = lexical_score_threshold

    @traceable(name="support_agent_chat")
    def chat(self, message: str) -> ChatResponse:
        question = message.strip()
        if not question:
            raise ValueError("消息不能为空")

        retrieved = self.vector_store.search(question, self.top_k)
        top_score = retrieved[0].score if retrieved else 0.0
        top_lexical_score = retrieved[0].lexical_score if retrieved else 0.0
        low_confidence = (
            not retrieved
            or top_score < self.score_threshold
            or top_lexical_score < self.lexical_score_threshold
        )
        explicit_escalation = self._is_escalation_request(question)

        citations = [
            Citation(
                source=chunk.source,
                chunk_id=chunk.chunk_id,
                score=round(chunk.score, 4),
                snippet=chunk.snippet,
            )
            for chunk in retrieved
        ]

        if low_confidence or explicit_escalation:
            reason = self._build_ticket_reason(low_confidence, explicit_escalation, top_score)
            summary = self.responder.build_ticket_summary(question, reason, retrieved)
            ticket = self.ticket_service.create_ticket(question, reason, summary)
            return ChatResponse(
                mode="ticket",
                citations=citations,
                ticket=ticket,
                retrieval_score=round(top_score, 4),
                debug={
                    "decision": "create_ticket",
                    "low_confidence": low_confidence,
                    "explicit_escalation": explicit_escalation,
                    "score_threshold": self.score_threshold,
                    "lexical_score_threshold": self.lexical_score_threshold,
                    "top_lexical_score": round(top_lexical_score, 4),
                },
            )

        answer = self.responder.build_answer(question, retrieved)
        return ChatResponse(
            mode="answer",
            answer=answer,
            citations=citations,
            retrieval_score=round(top_score, 4),
            debug={
                "decision": "answer_from_rag",
                "low_confidence": low_confidence,
                "explicit_escalation": explicit_escalation,
                "score_threshold": self.score_threshold,
                "lexical_score_threshold": self.lexical_score_threshold,
                "top_lexical_score": round(top_lexical_score, 4),
            },
        )

    def _is_escalation_request(self, question: str) -> bool:
        return any(phrase in question for phrase in ESCALATION_PHRASES)

    def _build_ticket_reason(
        self,
        low_confidence: bool,
        explicit_escalation: bool,
        top_score: float,
    ) -> str:
        if low_confidence and explicit_escalation:
            return f"用户要求升级处理，且知识库命中不足（Top1={top_score:.2f}）"
        if explicit_escalation:
            return "用户明确要求升级处理"
        return f"知识库未命中有效结果（Top1={top_score:.2f}）"
