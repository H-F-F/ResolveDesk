from __future__ import annotations

import re


class TextChunker:
    def __init__(self, chunk_size: int, overlap: int) -> None:
        self.chunk_size = chunk_size
        self.overlap = overlap

    def split(self, text: str) -> list[str]:
        normalized = self._normalize(text)
        if not normalized:
            return []
        if len(normalized) <= self.chunk_size:
            return [normalized]

        chunks: list[str] = []
        start = 0
        text_length = len(normalized)

        while start < text_length:
            end = min(start + self.chunk_size, text_length)
            if end < text_length:
                newline_break = normalized.rfind("\n", start, end)
                if newline_break > start + (self.chunk_size // 2):
                    end = newline_break

            chunk = normalized[start:end].strip()
            if chunk:
                chunks.append(chunk)

            if end >= text_length:
                break

            start = max(end - self.overlap, start + 1)

        return chunks

    def _normalize(self, text: str) -> str:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

