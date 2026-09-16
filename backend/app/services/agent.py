from __future__ import annotations

import json
import logging
from typing import Any

from ..schemas import ChatResponse, Citation, TicketRecord
from ..tracing import traceable
from .contracts import AgentToolCall, AgentToolTurn
from .conversations import ConversationService
from .domain import RetrievedChunk
from .responder import SupportResponder
from .tickets import TicketService
from .vector_store import VectorStore

logger = logging.getLogger(__name__)


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

AGENT_SYSTEM_PROMPT = (
    "你是企业 IT 支持助手 Agent。你通过工具调用完成工作：\n"
    "1. 收到用户问题后，先调用 search_knowledge 工具检索企业知识库，"
    "除非用户明显是在要求创建工单或转人工。\n"
    "2. 如果检索结果足以回答问题，基于检索到的片段直接回答，给出简洁、可执行的步骤，"
    "并注明依据的文档名；不要编造知识库中没有的内容。\n"
    "3. 如果检索结果不足、问题超出知识库范围，或用户明确要求转人工/创建工单，"
    "调用 create_ticket 工具。\n"
    "4. 如果用户是在追问上一条回答（例如说“还是不行”“试过了还是不行”），"
    "说明前序方案未解决，此时应调用 create_ticket 工具升级处理。\n"
    "5. 回答使用简洁中文。"
)

AGENT_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_knowledge",
            "description": (
                "在企业 IT 知识库中检索与用户问题相关的文档片段，"
                "返回最相关的若干片段、来源文档名和匹配得分。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "用于检索的查询语句，通常直接使用用户问题。",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_ticket",
            "description": (
                "为用户创建一条升级工单。适用于知识库无法解决问题、"
                "前序方案无效，或用户明确要求转人工的场景。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "用户问题原文。",
                    },
                    "reason": {
                        "type": "string",
                        "description": "创建工单的原因。",
                    },
                },
                "required": ["question", "reason"],
            },
        },
    },
]

MAX_TOOL_ITERATIONS = 4


class SupportAgent:
    def __init__(
        self,
        vector_store: VectorStore,
        responder: SupportResponder,
        ticket_service: TicketService,
        conversations: ConversationService,
        top_k: int,
        score_threshold: float,
        lexical_score_threshold: float,
    ) -> None:
        self.vector_store = vector_store
        self.responder = responder
        self.ticket_service = ticket_service
        self.conversations = conversations
        self.top_k = top_k
        self.score_threshold = score_threshold
        self.lexical_score_threshold = lexical_score_threshold

    @traceable(name="support_agent_chat")
    def chat(self, message: str, session_id: str | None = None) -> ChatResponse:
        question = message.strip()
        if not question:
            raise ValueError("消息不能为空")

        session_id = self.conversations.get_or_create_session(session_id)

        if self.responder.chat_client is not None:
            response = self._chat_with_tools(question, session_id)
        else:
            response = self._chat_heuristic(question, session_id)

        self.conversations.append_message(session_id, "user", question)
        assistant_note = response.answer or (
            f"已为您创建工单 {response.ticket.ticket_no}：{response.ticket.summary}"
            if response.ticket is not None
            else "（无输出）"
        )
        self.conversations.append_message(session_id, "assistant", assistant_note)

        return response

    # ------------------------------------------------------------------
    # Tool-calling path (LLM available)
    # ------------------------------------------------------------------

    def _chat_with_tools(self, question: str, session_id: str) -> ChatResponse:
        messages = self._build_messages(question, session_id)
        retrieval_hits: list[RetrievedChunk] = []
        created_ticket: TicketRecord | None = None
        final_text: str | None = None
        executed_tools: list[str] = []
        iterations = 0

        while iterations < MAX_TOOL_ITERATIONS:
            iterations += 1
            turn = self.responder.chat_client.complete_with_tools(messages, AGENT_TOOLS)
            if not turn.has_tool_calls:
                final_text = (turn.content or "").strip() or None
                break

            messages.append(self._assistant_tool_message(turn))
            for call in turn.tool_calls:
                executed_tools.append(call.name)
                if call.name == "search_knowledge":
                    hits, tool_content = self._execute_search(call)
                    retrieval_hits = hits
                    messages.append(
                        {"role": "tool", "tool_call_id": call.call_id, "content": tool_content}
                    )
                elif call.name == "create_ticket":
                    ticket, tool_content = self._execute_create_ticket(call, question, retrieval_hits)
                    created_ticket = ticket
                    messages.append(
                        {"role": "tool", "tool_call_id": call.call_id, "content": tool_content}
                    )
                else:
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.call_id,
                            "content": f"未知工具：{call.name}",
                        }
                    )
        else:
            final_text = final_text or "知识库中没有找到可用答案。"

        citations = [
            Citation(
                source=chunk.source,
                chunk_id=chunk.chunk_id,
                score=round(chunk.score, 4),
                snippet=chunk.snippet,
            )
            for chunk in retrieval_hits
        ]
        top_score = retrieval_hits[0].score if retrieval_hits else 0.0

        if created_ticket is not None:
            return ChatResponse(
                mode="ticket",
                citations=citations,
                ticket=created_ticket,
                retrieval_score=round(top_score, 4) if retrieval_hits else None,
                session_id=session_id,
                debug={
                    "decision": "tool_loop",
                    "iterations": iterations,
                    "tools_executed": executed_tools,
                    "provider": self.responder.provider_name,
                    "model": self.responder.model_name,
                },
            )

        return ChatResponse(
            mode="answer",
            answer=final_text or self.responder.build_answer(question, retrieval_hits),
            citations=citations,
            retrieval_score=round(top_score, 4) if retrieval_hits else None,
            session_id=session_id,
            debug={
                "decision": "tool_loop",
                "iterations": iterations,
                "tools_executed": executed_tools,
                "provider": self.responder.provider_name,
                "model": self.responder.model_name,
            },
        )

    def _build_messages(self, question: str, session_id: str) -> list[dict]:
        messages: list[dict] = [{"role": "system", "content": AGENT_SYSTEM_PROMPT}]
        for item in self.conversations.list_messages(session_id):
            if item.role in {"user", "assistant"}:
                messages.append({"role": item.role, "content": item.content})
        messages.append({"role": "user", "content": question})
        return messages

    def _assistant_tool_message(self, turn: AgentToolTurn) -> dict:
        return {
            "role": "assistant",
            "content": turn.content,
            "tool_calls": [
                {
                    "id": call.call_id,
                    "type": "function",
                    "function": {"name": call.name, "arguments": call.arguments},
                }
                for call in turn.tool_calls
            ],
        }

    def _execute_search(self, call: AgentToolCall) -> tuple[list[RetrievedChunk], str]:
        args = self._parse_arguments(call)
        query = str(args.get("query") or "").strip() or "知识库检索"
        hits = self.vector_store.search(query, self.top_k)
        if not hits:
            return hits, "知识库中没有找到相关文档。"
        rendered_lines = [
            f"[{index}] source={hit.source} score={hit.score:.4f}\n{hit.text}"
            for index, hit in enumerate(hits, start=1)
        ]
        return hits, "\n\n".join(rendered_lines)

    def _execute_create_ticket(
        self,
        call: AgentToolCall,
        fallback_question: str,
        retrieval_hits: list[RetrievedChunk],
    ) -> tuple[TicketRecord, str]:
        args = self._parse_arguments(call)
        question = str(args.get("question") or "").strip() or fallback_question
        reason = str(args.get("reason") or "").strip() or "LLM 判定需要升级处理"
        summary = self.responder.build_ticket_summary(question, reason, retrieval_hits)
        ticket = self.ticket_service.create_ticket(question, reason, summary)
        return ticket, f"已创建工单 {ticket.ticket_no}，原因：{reason}"

    @staticmethod
    def _parse_arguments(call: AgentToolCall) -> dict[str, Any]:
        try:
            parsed = json.loads(call.arguments or "{}")
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, TypeError):
            logger.warning("Tool call arguments are not valid JSON: %s", call.arguments)
        return {}

    # ------------------------------------------------------------------
    # Heuristic fallback path (offline mode, no LLM)
    # ------------------------------------------------------------------

    def _chat_heuristic(self, question: str, session_id: str) -> ChatResponse:
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
                session_id=session_id,
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
            session_id=session_id,
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
