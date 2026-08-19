from __future__ import annotations

import re


CHINESE_PATTERN = re.compile(r"[\u4e00-\u9fff]+")
LATIN_PATTERN = re.compile(r"[a-z0-9_]+")
PART_PATTERN = re.compile(r"[\u4e00-\u9fff]+|[a-z0-9_]+")

ALIASES = (
    ("\u8fde\u4e0d\u4e0a\u600e\u4e48\u529e", "\u8fde\u63a5\u5931\u8d25"),
    ("\u8fde\u63a5\u4e0d\u4e0a", "\u8fde\u63a5\u5931\u8d25"),
    ("\u8fde\u4e0d\u4e0a", "\u8fde\u63a5\u5931\u8d25"),
    ("\u767b\u5f55\u4e0d\u4e0a", "\u65e0\u6cd5\u767b\u5f55"),
    ("\u767b\u4e0d\u4e0a", "\u65e0\u6cd5\u767b\u5f55"),
    ("\u767b\u4e0d\u8fdb\u53bb", "\u65e0\u6cd5\u767b\u5f55"),
    ("\u6253\u4e0d\u5f00", "\u65e0\u6cd5\u6253\u5f00"),
    ("\u6253\u5370\u4e0d\u4e86", "\u65e0\u6cd5\u6253\u5370"),
    ("\u6253\u4e0d\u5370", "\u65e0\u6cd5\u6253\u5370"),
    ("\u4e0a\u4e0d\u4e86\u7f51", "\u65e0\u6cd5\u8054\u7f51"),
    ("\u5bc6\u7801\u4e0d\u5bf9", "\u5bc6\u7801\u9519\u8bef"),
    ("\u5bc6\u7801\u9519", "\u5bc6\u7801\u9519\u8bef"),
)

PHRASE_STOPWORDS = {
    "\u600e\u4e48\u529e",
    "\u600e\u4e48\u5904\u7406",
    "\u600e\u4e48",
    "\u5e2e\u6211",
    "\u8bf7\u95ee",
    "\u4e00\u4e0b",
}

TOKEN_STOPWORDS = {
    "\u516c\u53f8",
    "\u7cfb\u7edf",
    "\u5904\u7406",
    "\u6545\u969c",
    "\u95ee\u9898",
    "\u6807\u9898",
    "\u9002\u7528\u573a\u666f",
    "\u5904\u7406\u6b65\u9aa4",
    "\u8865\u5145\u8bf4\u660e",
    "\u5347\u7ea7\u6761\u4ef6",
    "\u65e0\u6cd5",
    "\u4ecd\u7136",
    "\u4ecd\u65e7",
}


def normalize_text(text: str) -> str:
    normalized = text.lower()
    for source, target in ALIASES:
        normalized = normalized.replace(source, target)
    for stopword in PHRASE_STOPWORDS:
        normalized = normalized.replace(stopword, " ")
    return normalized


def tokenize_text(text: str) -> list[str]:
    tokens: list[str] = []

    for part in PART_PATTERN.findall(normalize_text(text)):
        if LATIN_PATTERN.fullmatch(part):
            tokens.append(part)
            continue

        if not CHINESE_PATTERN.fullmatch(part) or len(part) <= 1:
            continue

        tokens.append(part)
        tokens.extend(part[index : index + 2] for index in range(len(part) - 1))
        if len(part) > 2:
            tokens.extend(part[index : index + 3] for index in range(len(part) - 2))

    return [token for token in tokens if token not in TOKEN_STOPWORDS]


def token_weight(token: str) -> float:
    if LATIN_PATTERN.fullmatch(token):
        return 2.0
    if len(token) >= 3:
        return 1.4
    return 1.0


def lexical_coverage_score(query_text: str, text: str) -> float:
    query_tokens = set(tokenize_text(query_text))
    if not query_tokens:
        return 0.0

    document_tokens = set(tokenize_text(text))
    overlap = query_tokens & document_tokens

    overlap_weight = sum(token_weight(token) for token in overlap)
    total_weight = sum(token_weight(token) for token in query_tokens) or 1.0
    return overlap_weight / total_weight
