"""Embedding 服务包：Embedder 协议 + OpenAI 兼容实现 + Fake（测试）。

create_embedder 的 settings 鸭子读取 embedding_* 字段（Settings 与测试
SimpleNamespace 均可）：配了 api_key → OpenAI 兼容端点；否则 Fake。
"""
from app.core.config import Settings
from app.services.embedding.base import EmbeddingError, Embedder  # noqa: F401
from app.services.embedding.fakes import FakeEmbedder  # noqa: F401
from app.services.embedding.openai_compatible import OpenAIEmbedder  # noqa: F401

__all__ = ["Embedder", "EmbeddingError", "FakeEmbedder", "OpenAIEmbedder", "create_embedder"]


def create_embedder(settings: Settings) -> Embedder:
    if settings.embedding_api_key:
        return OpenAIEmbedder(
            base_url=settings.embedding_base_url,
            api_key=settings.embedding_api_key,
            model=settings.embedding_model,
            dim=settings.embedding_dim,
            batch_size=settings.embedding_batch_size,
        )
    return FakeEmbedder(dim=settings.embedding_dim)
