"""VectorClient 协议与数据契约（Plan 1 Task 9）。

MySQL chunk.id 兼作 Milvus 主键（架构约定），kb_id 为 partition key，
检索只按 kb 隔离 + enabled 过滤，score 为 COSINE 相似度（越大越近）。
"""
from dataclasses import dataclass
from typing import Protocol


@dataclass
class VectorRow:
    """入库一行 chunk 向量（与 Milvus schema 字段一一对应）。"""

    id: int
    vector: list[float]
    chunk_text: str
    page_number: int | None
    doc_id: int
    kb_id: int
    enabled: bool


@dataclass
class SearchHit:
    """检索命中：chunk 定位信息 + 相似度分数。"""

    chunk_id: int
    doc_id: int
    kb_id: int
    score: float
    chunk_text: str
    page_number: int | None


class VectorClient(Protocol):
    def ensure_collection(self) -> None:
        """幂等建 collection + 索引（已存在则跳过）。"""
        ...

    def insert(self, rows: list[VectorRow]) -> None:
        """批量写入 chunk 向量。"""
        ...

    def search(
        self,
        query_vector: list[float],
        kb_ids: list[int],
        top_k: int = 5,
        threshold: float | None = None,
    ) -> list[SearchHit]:
        """在指定 kb 内检索，按相似度降序返回 top_k 条；threshold 时滤掉低分。"""
        ...

    def delete_by_doc(self, doc_id: int) -> None:
        """删除整个文档的全部向量（删文档链路第一步，红线 3）。"""
        ...

    def delete_by_ids(self, ids: list[int]) -> None:
        """按 chunk id 精准删除（替换 / md 编辑后清旧向量，红线 2）。"""
        ...

    def set_doc_enabled(self, doc_id: int, enabled: bool) -> None:
        """整文档启用/停用：query 取回含 vector 后翻标志 upsert。"""
        ...

    def count_by_doc(self, doc_id: int) -> int:
        """文档在 Milvus 的残留行数（清库校验用）。"""
        ...
