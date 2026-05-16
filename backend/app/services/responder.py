from __future__ import annotations

import logging
import re
from typing import Any

import requests

from ..tracing import traceable
from .contracts import ChatCompletionClient
from .domain import RetrievedChunk


logger = logging.getLogger(__name__)


class OpenAICompatibleChatClient:
    provider_name = "openai_compatible"

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model_name: str,
        *,
        timeout_seconds: float = 60.0,
        temperature: float = 0.2,
        verify_ssl: bool = True,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model_name = model_name
        self.timeout_seconds = timeout_seconds
        self.temperature = temperature
        self.verify_ssl = verify_ssl

    @traceable(name="chat_completion_openai_compatible")
    def complete(self, system_prompt: str, user_prompt: str) -> str:
        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model_name,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": self.temperature,
                "stream": False,
            },
            timeout=self.timeout_seconds,
            verify=self.verify_ssl,
        )
        self._raise_for_status(response)

        payload = response.json()
        choices = payload.get("choices", [])
        if not isinstance(choices, list) or not choices:
            raise ValueError("Chat 接口返回结果为空")

        message = choices[0].get("message", {})
        content = message.get("content", "")
        rendered = self._render_content(content).strip()
        if not rendered:
            raise ValueError("Chat 接口未返回文本内容")
        return rendered

    def _render_content(self, content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(str(item.get("text", "")))
            return "\n".join(part for part in parts if part)
        return str(content or "")

    def _raise_for_status(self, response: requests.Response) -> None:
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            logger.exception("Chat request failed with status %s", response.status_code)
            detail = self._extract_error_detail(response)
            raise ValueError(f"Chat 接口调用失败: {detail}") from exc

    def _extract_error_detail(self, response: requests.Response) -> str:
        try:
            payload: Any = response.json()
        except ValueError:
            payload = None

        if isinstance(payload, dict):
            if isinstance(payload.get("error"), dict) and payload["error"].get("message"):
                return str(payload["error"]["message"])
            if payload.get("message"):
                return str(payload["message"])
        return response.text[:200] or f"HTTP {response.status_code}"


class SupportResponder:
    provider_name = "offline"
    model_name = "heuristic-responder"

    def __init__(self, chat_client: ChatCompletionClient | None = None) -> None:
        self.chat_client = chat_client
        if chat_client is not None:
            self.provider_name = chat_client.provider_name
            self.model_name = chat_client.model_name

    def build_answer(self, question: str, chunks: list[RetrievedChunk]) -> str:
        if self.chat_client is not None:
            try:
                return self._build_llm_answer(question, chunks)
            except Exception:
                logger.exception("LLM answer generation failed, falling back to heuristic responder")
        return self._build_heuristic_answer(question, chunks)

    def build_ticket_summary(
        self,
        question: str,
        reason: str,
        chunks: list[RetrievedChunk],
    ) -> str:
        if self.chat_client is not None:
            try:
                return self._build_llm_ticket_summary(question, reason, chunks)
            except Exception:
                logger.exception("LLM ticket summary generation failed, falling back to heuristic summary")
        return self._build_heuristic_ticket_summary(question, reason, chunks)

    def _build_llm_answer(self, question: str, chunks: list[RetrievedChunk]) -> str:
        if not chunks:
            return "知识库中没有找到可用答案。"

        system_prompt = (
            "你是企业 IT 支持助手。"
            "你只能基于提供的知识库片段回答，不要编造不存在的步骤或系统。"
            "输出使用简洁中文，优先给出可执行步骤。"
        )
        user_prompt = (
            f"用户问题：{question}\n\n"
            f"知识库上下文：\n{self._render_chunks(chunks)}\n\n"
            "请按以下要求输出：\n"
            "1. 直接回答如何处理。\n"
            "2. 如果有步骤，请整理成 3 到 6 条编号步骤。\n"
            "3. 如果有补充参考文档，请单独一行写“补充参考：文档名”。\n"
            "4. 最后一行提醒：如果试过仍不行，可以回复“试过了还是不行”创建工单。\n"
            "5. 不要输出与知识库无关的内容。"
        )
        return self.chat_client.complete(system_prompt, user_prompt)

    def _build_llm_ticket_summary(
        self,
        question: str,
        reason: str,
        chunks: list[RetrievedChunk],
    ) -> str:
        system_prompt = (
            "你是企业 IT 支持系统的工单摘要助手。"
            "请基于给定问题、升级原因和检索结果，生成一条简洁准确的中文工单摘要。"
        )
        user_prompt = (
            f"用户问题：{question}\n"
            f"升级原因：{reason}\n"
            f"检索结果：\n{self._render_chunks(chunks) if chunks else '无有效结果'}\n\n"
            "请输出一行中文摘要，包含问题、原因和最相关文档。"
        )
        return self.chat_client.complete(system_prompt, user_prompt).replace("\n", " ").strip()

    def _build_heuristic_answer(self, question: str, chunks: list[RetrievedChunk]) -> str:
        if not chunks:
            return "知识库中没有找到可用答案。"

        primary = chunks[0]
        action_lines = self._extract_action_lines(primary.text)

        lines = ["根据知识库内容，建议按以下步骤处理："]
        if action_lines:
            for index, line in enumerate(action_lines[:4], start=1):
                lines.append(f"{index}. {line}")
        else:
            lines.append(primary.snippet or primary.text[:120])

        if len(chunks) > 1:
            references = "、".join(chunk.source for chunk in chunks[1:])
            lines.append(f"补充参考文档：{references}")

        lines.append("如果你已经按上述步骤处理但仍未恢复，可以直接回复“试过了还是不行”，系统会自动创建工单。")
        return "\n".join(lines)

    def _build_heuristic_ticket_summary(
        self,
        question: str,
        reason: str,
        chunks: list[RetrievedChunk],
    ) -> str:
        if chunks:
            top_chunk = chunks[0]
            return (
                f"用户问题：{question}；升级原因：{reason}；"
                f"检索最高命中文档：{top_chunk.source}；"
                f"参考片段：{top_chunk.snippet}"
            )
        return f"用户问题：{question}；升级原因：{reason}；知识库未命中有效结果。"

    def _render_chunks(self, chunks: list[RetrievedChunk]) -> str:
        rendered: list[str] = []
        for index, chunk in enumerate(chunks, start=1):
            rendered.append(
                (
                    f"[{index}] source={chunk.source} score={chunk.score:.4f}\n"
                    f"{chunk.text}"
                )
            )
        return "\n\n".join(rendered)

    def _extract_action_lines(self, text: str) -> list[str]:
        candidates = [line.strip(" -\t") for line in text.splitlines() if line.strip()]
        prioritized: list[str] = []

        for line in candidates:
            if re.match(r"^(\d+[.)、]|步骤|处理步骤|建议|现象|升级条件)", line):
                prioritized.append(line)
            elif 8 <= len(line) <= 60:
                prioritized.append(line)

        deduplicated: list[str] = []
        seen: set[str] = set()
        for line in prioritized:
            if line not in seen:
                deduplicated.append(line)
                seen.add(line)
        return deduplicated
