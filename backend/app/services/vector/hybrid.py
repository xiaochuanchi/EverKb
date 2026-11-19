"""混合检索编排层（二期 Task 25）：向量稠密路 + BM25 稀疏路 + RRF 融合。

定位（计划文档 Global Constraints）：HybridRetriever 是 `VectorClient` 之上的
编排层，**不是新的存储抽象**——稠密路复用既有 `vector.search`，稀疏路走
`BM25Index.search`，两路结果经 RRF 融合，不改变既有检索语义。

RRF 公式钉死（计划文档）：RRF(d) = Σ_{r∈R} 1/(k + rank_r(d))，k=60。
- 稠密与稀疏分数量纲不可比（COSINE vs BM25），**只按各自 rank 融合，不做加权**；
- 两路各自独立检索（oversample 放大 top_k），停用/删除文档在两路都被过滤
  （红线：不破坏既有 enabled 过滤语义）；
- 融合分按 chunk_id 聚合（两路命中同一 chunk 时 rank 相加，source="both"）。
"""
from __future__ import annotations

from dataclasses import dataclass

from app.services.vector.base import VectorClient
from app.services.vector.bm25 import BM25Index


@dataclass
class HybridHit:
    """混合检索命中：chunk 定位信息 + RRF 融合分 + 来源标记。"""

    chunk_id: int
    score: float            # RRF 融合分（仅排序用，量纲非相似度）
    source: str             # "dense" | "sparse" | "both"
    chunk_text: str
    doc_id: int
    kb_id: int
    page_number: int | None


class HybridRetriever:
    """向量 + BM25 两路检索，RRF 融合排序。"""

    def __init__(self, vector: VectorClient, bm25: BM25Index, *, rrf_k: int = 60) -> None:
        self._vector = vector
        self._bm25 = bm25
        self._rrf_k = rrf_k

    def search(
        self,
        query: str,
        query_vector: list[float],
        *,
        kb_ids: list[int],
        top_k: int = 5,
        threshold: float | None = None,
        oversample: int = 4,
    ) -> list[HybridHit]:
        """两路检索 → RRF 融合 → 截断 top_k。

        query：原始文本（BM25 稀疏路用）；query_vector：稠密路用（由编排层在
        embedding span 内产出，与 rag.retrieve 的契约一致）。
        threshold 仅作用于稠密路的相似度过滤（BM25 分数无量纲，不适用）。
        """
        if not kb_ids:
            return []
        fetch_k = top_k * max(1, oversample)
        # 稠密路（COSINE，越大越近）
        dense_hits = self._vector.search(query_vector, kb_ids, top_k=fetch_k, threshold=threshold)
        # 稀疏路（BM25）
        sparse_hits = self._bm25.search(query, kb_ids, top_k=fetch_k)

        # RRF 融合：chunk_id → 累计融合分；记录来源
        fused: dict[int, float] = {}
        source: dict[int, str] = {}
        for rank, h in enumerate(dense_hits, start=1):
            fused[h.chunk_id] = fused.get(h.chunk_id, 0.0) + 1.0 / (self._rrf_k + rank)
            source[h.chunk_id] = "dense"
        for rank, h in enumerate(sparse_hits, start=1):
            fused[h.chunk_id] = fused.get(h.chunk_id, 0.0) + 1.0 / (self._rrf_k + rank)
            source[h.chunk_id] = "both" if source.get(h.chunk_id) == "dense" else "sparse"

        # 命中详情（两路共有的 chunk 取稠密路的文本/定位，字段一致）
        detail: dict[int, tuple[str, int, int, int | None]] = {}
        for h in dense_hits:
            detail[h.chunk_id] = (h.chunk_text, h.doc_id, h.kb_id, h.page_number)
        for h in sparse_hits:
            if h.chunk_id not in detail:
                detail[h.chunk_id] = (h.chunk_text, h.doc_id, h.kb_id, h.page_number)

        ranked = sorted(fused.items(), key=lambda kv: kv[1], reverse=True)[:top_k]
        return [
            HybridHit(
                chunk_id=cid,
                score=score,
                source=source[cid],
                chunk_text=detail[cid][0],
                doc_id=detail[cid][1],
                kb_id=detail[cid][2],
                page_number=detail[cid][3],
            )
            for cid, score in ranked
        ]
