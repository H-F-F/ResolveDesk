from __future__ import annotations

from ..config import Settings
from .contracts import TextEmbedder
from .embedder import LocalHashEmbedder, OpenAICompatibleEmbedder
from .responder import OpenAICompatibleChatClient, SupportResponder


def build_embedder(settings: Settings) -> TextEmbedder:
    provider = settings.embedding_provider.strip().lower()
    if provider == "offline":
        return LocalHashEmbedder(settings.embedding_dimension)
    if provider == "openai_compatible":
        _ensure_model_config(settings, require_chat=False, require_embedding=True)
        return OpenAICompatibleEmbedder(
            base_url=settings.model_api_base,
            api_key=settings.model_api_key,
            model_name=settings.embedding_model_name,
            timeout_seconds=settings.model_timeout_seconds,
            verify_ssl=settings.model_verify_ssl,
        )
    raise ValueError(f"不支持的 embedding provider: {settings.embedding_provider}")


def build_responder(settings: Settings) -> SupportResponder:
    provider = settings.chat_provider.strip().lower()
    if provider == "offline":
        return SupportResponder()
    if provider == "openai_compatible":
        _ensure_model_config(settings, require_chat=True, require_embedding=False)
        client = OpenAICompatibleChatClient(
            base_url=settings.model_api_base,
            api_key=settings.model_api_key,
            model_name=settings.chat_model_name,
            timeout_seconds=settings.model_timeout_seconds,
            temperature=settings.model_temperature,
            verify_ssl=settings.model_verify_ssl,
        )
        return SupportResponder(chat_client=client)
    raise ValueError(f"不支持的 chat provider: {settings.chat_provider}")


def _ensure_model_config(settings: Settings, *, require_chat: bool, require_embedding: bool) -> None:
    missing: list[str] = []
    if not settings.model_api_base:
        missing.append("MODEL_API_BASE")
    if not settings.model_api_key:
        missing.append("MODEL_API_KEY")
    if require_chat and not settings.chat_model_name:
        missing.append("CHAT_MODEL_NAME")
    if require_embedding and not settings.embedding_model_name:
        missing.append("EMBEDDING_MODEL_NAME")
    if missing:
        raise ValueError(f"模型配置不完整，缺少: {', '.join(missing)}")
