"""BM25 稀疏检索索引（二期 Task 25）：纯内存倒排 + 词频统计，确定性、无网络。

选型：手写 BM25 + jieba 分词，而非 Milvus 2.5
内置 BM25（Function + BM25EmbeddingFunction）。理由：

1. 规避 pymilvus 2.5 稀疏向量 API 的版本兼容风险（已识别为主要风险点）；
2. 稀疏路与稠密路解耦——BM25 是 HybridRetriever 的独立「稀疏路」索引，
   生产与测试共用同一实现（Fake 不再需要单独模拟稀疏语义）；
3. 实现透明：亲手实现 BM25 统计量 + RRF 融合，行为完全可控，能讲清「何时关键词好」。

BM25 公式（经典 Okapi BM25，k1=1.5, b=0.75）：
  score(q, d) = Σ_{t∈q} IDF(t) · f(t,d)·(k1+1) / (f(t,d) + k1·(1−b+b·|d|/avgdl))
  IDF(t) = ln((N − n(t) + 0.5) / (n(t) + 0.5) + 1)

纪律：
- 索引随 insert 同步构建，delete_by_doc / delete_by_ids / set_doc_enabled 同步维护；
- 停用（enabled=False）的 chunk 不参与检索（与稠密路一致，红线：不破坏既有过滤语义）；
- 文本用 jieba.lcut 分词，token 即词；IDF 分母 +0.5 平滑，空索引返回空结果。
"""
from __future__ import annotations

import math
from collections import defaultdict

import jieba

from app.services.vector.base import SearchHit


class BM25Index:
    """内存 BM25 索引：doc 即 chunk（chunk_id 为文档主键）。"""

    def __init__(self, *, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        # chunk_id → (tokens, kb_id, doc_id, enabled, chunk_text, page_number)
        self._docs: dict[int, tuple[list[str], int, int, bool, str, int | None]] = {}
        # token → {chunk_id: 词频}
        self._postings: dict[str, dict[int, int]] = defaultdict(dict)
        self._doc_len: dict[int, int] = {}  # chunk_id → 文档长度（token 数）
        self._avgdl: float = 0.0
        self._n_docs: int = 0  # 参与统计的文档数（含停用？不含——见下）

    # ── 索引维护 ──────────────────────────────────────────────

    def add(
        self,
        chunk_id: int,
        text: str,
        *,
        doc_id: int,
        kb_id: int,
        enabled: bool = True,
        page_number: int | None = None,
    ) -> None:
        """插入/覆盖一个 chunk 的索引（chunk_id 幂等，后写覆盖）。"""
        tokens = _tokenize(text)
        # 覆盖旧词频：先从 postings 移除旧 tokens 的计数
        if chunk_id in self._docs:
            self._remove_doc_from_postings(chunk_id)
        self._docs[chunk_id] = (tokens, kb_id, doc_id, enabled, text, page_number)
        self._doc_len[chunk_id] = len(tokens)
        for tok in tokens:
            self._postings[tok][chunk_id] = self._postings[tok].get(chunk_id, 0) + 1
        self._refresh_stats()

    def delete_by_doc(self, doc_id: int) -> None:
        """删除整文档的全部 chunk 索引。"""
        for cid in [c for c, meta in self._docs.items() if meta[2] == doc_id]:
            self._remove_chunk(cid)
        self._refresh_stats()

    def delete_by_ids(self, ids: list[int]) -> None:
        """按 chunk id 精准删除。"""
        for cid in ids:
            if cid in self._docs:
                self._remove_chunk(cid)
        self._refresh_stats()

    def set_doc_enabled(self, doc_id: int, enabled: bool) -> None:
        """翻整文档的 enabled 标志（停用 = 不参与检索）。"""
        for cid, meta in list(self._docs.items()):
            if meta[2] == doc_id:
                tokens, kb_id, _doc, _en, text, page = meta
                self._docs[cid] = (tokens, kb_id, _doc, enabled, text, page)
        self._refresh_stats()

    # ── 检索 ──────────────────────────────────────────────────

    def search(self, query: str, kb_ids: list[int], top_k: int = 5) -> list[SearchHit]:
        """按 BM25 分数降序返回 top_k；停用 chunk 与 kb 外 chunk 均不参与。"""
        if not kb_ids or self._n_docs == 0:
            return []
        kb_set = set(kb_ids)
        qtoks = _tokenize(query)
        if not qtoks:
            return []
        scores: dict[int, float] = defaultdict(float)
        for tok in qtoks:
            idf = self._idf(tok)
            if idf == 0.0:
                continue
            for cid, tf in self._postings.get(tok, {}).items():
                meta = self._docs.get(cid)
                if meta is None or meta[1] not in kb_set or not meta[3]:
                    continue  # kb 外 / 停用
                dl = self._doc_len.get(cid, 0)
                denom = tf + self.k1 * (1 - self.b + self.b * (dl / self._avgdl if self._avgdl else 1.0))
                scores[cid] += idf * (tf * (self.k1 + 1)) / denom
        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:top_k]
        hits: list[SearchHit] = []
        for cid, score in ranked:
            meta = self._docs[cid]
            hits.append(SearchHit(
                chunk_id=cid,
                doc_id=meta[2],
                kb_id=meta[1],
                score=score,
                chunk_text=meta[4],
                page_number=meta[5],
            ))
        return hits

    # ── 内部 ──────────────────────────────────────────────────

    def _remove_chunk(self, cid: int) -> None:
        self._remove_doc_from_postings(cid)
        self._docs.pop(cid, None)
        self._doc_len.pop(cid, None)

    def _remove_doc_from_postings(self, cid: int) -> None:
        """按该 chunk 的 token 列表逐个递减词频，空 posting 即删除。"""
        meta = self._docs.get(cid)
        if meta is None:
            return
        for tok in meta[0]:
            posting = self._postings.get(tok)
            if posting is None:
                continue
            posting.pop(cid, None)
            if not posting:
                self._postings.pop(tok, None)

    def _refresh_stats(self) -> None:
        """重算 N 与 avgdl。N 统计所有已索引文档（含停用），IDF 才符合全局统计。"""
        self._n_docs = len(self._docs)
        total_len = sum(self._doc_len.values())
        self._avgdl = total_len / self._n_docs if self._n_docs else 0.0

    def _idf(self, token: str) -> float:
        n = len(self._postings.get(token, {}))
        return math.log((self._n_docs - n + 0.5) / (n + 0.5) + 1.0)


def _tokenize(text: str) -> list[str]:
    """jieba 分词；返回非空白 token 列表。"""
    return [t.strip() for t in jieba.lcut(text) if t.strip()]
