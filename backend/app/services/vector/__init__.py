"""Vector 服务包：VectorClient 协议 + Milvus 实现 + Fake（测试）。

create_vector 按字段鸭子读取（Settings 与测试 SimpleNamespace 均可），
与 create_embedder 同款约定。
"""
from app.core.config import Settings
from app.services.vector.base import SearchHit, VectorClient, VectorRow  # noqa: F401
from app.services.vector.bm25 import BM25Index  # noqa: F401
from app.services.vector.fakes import FakeVector  # noqa: F401
from app.services.vector.hybrid import HybridHit, HybridRetriever  # noqa: F401
from app.services.vector.milvus import MilvusVectorClient  # noqa: F401

__all__ = [
    "BM25Index",
    "FakeVector",
    "HybridHit",
    "HybridRetriever",
    "MilvusVectorClient",
    "SearchHit",
    "VectorClient",
    "VectorRow",
    "create_vector",
]


def create_vector(settings: Settings) -> VectorClient:
    return MilvusVectorClient(
        uri=settings.milvus_uri,
        collection_name=settings.collection_name,
        dim=settings.embedding_dim,
    )
