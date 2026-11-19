"""BM25 索引管理器（二期混合检索接入生产）：进程级单例，启动全量加载 + 增量同步。

定位：BM25Index 是纯内存索引，评测脚本每次重建无妨，但生产 FastAPI 长驻进程
必须有一条生命周期——启动时从 MySQL 全量建索引，文档入库/删除/停用时增量同步，
否则索引与 MySQL/Milvus 漂移，直接违背一期「文档不腐烂」的红线。

线程安全：worker 线程（入库同步）与问答请求线程（检索）并发访问，故内置
threading.Lock 保护读改写。BM25Index 自身非线程安全，所有公开方法串行化。

同步点（红线 3 删除顺序对齐）：
- 入库成功（status=6 commit 后）→ add 新 chunk；
- 替换成功清旧 ids → delete_by_ids(old_ids)；
- 文档删除 → delete_by_doc(doc_id)；
- 文档停用/启用 → set_doc_enabled(doc_id, enabled)。
"""
from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from app.services.vector.bm25 import BM25Index
from app.services.vector.base import SearchHit

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models import Chunk


class BM25IndexManager:
    """BM25Index 的进程级封装：全量加载 + 增量同步 + 线程安全。"""

    def __init__(self, index: BM25Index | None = None) -> None:
        self._index = index if index is not None else BM25Index()
        self._lock = threading.Lock()
        self._loaded = False

    # ── 生命周期 ──────────────────────────────────────────────

    def load_from_db(self, session: Session) -> int:
        """从 MySQL 全量加载 enabled chunk 建索引，返回加载的 chunk 数。

        幂等：可重复调用（重新全量加载）。停用文档的 chunk 不载入
        （与稠密路 enabled 过滤语义一致）。
        """
        from sqlalchemy import select

        from app.models import Chunk, Document

        # enabled 文档的 chunk 才参与检索；document.enabled=False 的整档跳过
        rows = session.execute(
            select(Chunk, Document.enabled)
            .join(Document, Document.id == Chunk.document_id)
            .where(Document.enabled.is_(True))
        ).all()
        with self._lock:
            self._index = BM25Index()
            for chunk, _enabled in rows:
                self._index.add(
                    chunk.id,
                    chunk.content,
                    doc_id=chunk.document_id,
                    kb_id=chunk.kb_id,
                    enabled=True,
                    page_number=chunk.page_number,
                )
            self._loaded = True
        return len(rows)

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def size(self) -> int:
        with self._lock:
            return self._index._n_docs

    # ── 增量同步（入库/删除/停用触发）─────────────────────────

    def add_chunk(self, chunk: "Chunk", *, enabled: bool = True) -> None:
        """入库成功后同步一个 chunk（幂等，后写覆盖）。"""
        with self._lock:
            self._index.add(
                chunk.id,
                chunk.content,
                doc_id=chunk.document_id,
                kb_id=chunk.kb_id,
                enabled=enabled,
                page_number=chunk.page_number,
            )

    def add_chunks(self, chunks: list["Chunk"]) -> None:
        """批量同步 chunk（入库成功一次提交多 chunk）。"""
        with self._lock:
            for chunk in chunks:
                self._index.add(
                    chunk.id,
                    chunk.content,
                    doc_id=chunk.document_id,
                    kb_id=chunk.kb_id,
                    enabled=True,
                    page_number=chunk.page_number,
                )

    def delete_by_doc(self, doc_id: int) -> None:
        with self._lock:
            self._index.delete_by_doc(doc_id)

    def delete_by_ids(self, ids: list[int]) -> None:
        if not ids:
            return
        with self._lock:
            self._index.delete_by_ids(ids)

    def set_doc_enabled(self, doc_id: int, enabled: bool) -> None:
        with self._lock:
            self._index.set_doc_enabled(doc_id, enabled)

    # ── 检索（透传，加锁保证与同步串行）───────────────────────

    def search(self, query: str, kb_ids: list[int], top_k: int = 5) -> list[SearchHit]:
        with self._lock:
            return self._index.search(query, kb_ids, top_k=top_k)
