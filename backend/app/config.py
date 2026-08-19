from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from .env_loader import load_local_env


load_local_env()


ROOT_DIR = Path(__file__).resolve().parents[2]


def _env_str(name: str, default: str) -> str:
    return os.getenv(name, default)


def _env_str_from_names(names: tuple[str, ...], default: str) -> str:
    for name in names:
        value = os.getenv(name)
        if value is not None:
            return value
    return default


def _env_int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


def _env_int_from_names(names: tuple[str, ...], default: int) -> int:
    return int(_env_str_from_names(names, str(default)))


def _env_float(name: str, default: float) -> float:
    return float(os.getenv(name, str(default)))


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_path(name: str, default: Path) -> Path:
    value = os.getenv(name)
    return Path(value).expanduser() if value else default


def _default_storage_dir() -> Path:
    return _env_path("STORAGE_DIR", ROOT_DIR / "storage")


def _default_vector_store_dir() -> Path:
    return _env_path("VECTOR_STORE_DIR", _default_storage_dir() / "chroma")


def _default_sqlite_path() -> Path:
    return _env_path("SQLITE_PATH", _default_storage_dir() / "app.db")


def _default_logs_dir() -> Path:
    return _env_path("LOGS_DIR", _default_storage_dir() / "logs")


def _default_knowledge_base_dir() -> Path:
    return _env_path("KNOWLEDGE_BASE_DIR", ROOT_DIR / "data" / "knowledge_base")


@dataclass(frozen=True)
class Settings:
    app_name: str = field(default_factory=lambda: _env_str("APP_NAME", "IT Knowledge Ticket Assistant"))
    app_env: str = field(default_factory=lambda: _env_str("APP_ENV", "local"))
    log_level: str = field(default_factory=lambda: _env_str("LOG_LEVEL", "INFO"))
    frontend_api_base: str = field(default_factory=lambda: _env_str("FRONTEND_API_BASE", "http://localhost:8000"))
    chat_provider: str = field(default_factory=lambda: _env_str("CHAT_PROVIDER", "offline"))
    embedding_provider: str = field(default_factory=lambda: _env_str("EMBEDDING_PROVIDER", "offline"))
    model_api_base: str = field(default_factory=lambda: _env_str("MODEL_API_BASE", ""))
    model_api_key: str = field(default_factory=lambda: _env_str("MODEL_API_KEY", ""))
    chat_model_name: str = field(default_factory=lambda: _env_str("CHAT_MODEL_NAME", ""))
    embedding_model_name: str = field(default_factory=lambda: _env_str("EMBEDDING_MODEL_NAME", ""))
    model_timeout_seconds: float = field(default_factory=lambda: _env_float("MODEL_TIMEOUT_SECONDS", 60.0))
    model_temperature: float = field(default_factory=lambda: _env_float("MODEL_TEMPERATURE", 0.2))
    model_verify_ssl: bool = field(default_factory=lambda: _env_bool("MODEL_VERIFY_SSL", True))
    collection_name: str = field(default_factory=lambda: _env_str("CHROMA_COLLECTION", "it_knowledge_base"))
    rag_top_k: int = field(default_factory=lambda: _env_int("RAG_TOP_K", 3))
    rag_score_threshold: float = field(default_factory=lambda: _env_float("RAG_SCORE_THRESHOLD", 0.22))
    rag_lexical_score_threshold: float = field(default_factory=lambda: _env_float("RAG_LEXICAL_SCORE_THRESHOLD", 0.2))
    chunk_size: int = field(default_factory=lambda: _env_int("CHUNK_SIZE", 700))
    chunk_overlap: int = field(default_factory=lambda: _env_int("CHUNK_OVERLAP", 120))
    embedding_dimension: int = field(
        default_factory=lambda: _env_int_from_names(("EMBEDDING_DIMENSION", "LOCAL_EMBEDDING_DIMENSION"), 1536)
    )
    storage_dir: Path = field(default_factory=_default_storage_dir)
    vector_store_dir: Path = field(default_factory=_default_vector_store_dir)
    sqlite_path: Path = field(default_factory=_default_sqlite_path)
    logs_dir: Path = field(default_factory=_default_logs_dir)
    knowledge_base_dir: Path = field(default_factory=_default_knowledge_base_dir)

    def ensure_directories(self) -> None:
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.vector_store_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.knowledge_base_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
