"""混合检索（Task 25）：BM25 稀疏路 + 向量稠密路 + RRF 融合。

红线 3：测试不触网——FakeVector 稠密路 + BM25Index 稀疏路均为内存实现。

Review Focus 锁定（计划文档 §Review Focus 1/2）：
- RRF 用 rank 不用原始分（分数差异大但 rank 相同 → 融合分一致）；
- 停用文档在两路都被排除；
- source 标记 dense/sparse/both 正确；
- oversample 放大 top_k 生效。
"""
import pytest

from app.services.vector import BM25Index, FakeVector, HybridRetriever, VectorRow

DIM = 8
Q = [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]


def _vec(*comps: float) -> list[float]:
    return [float(c) for c in comps] + [0.0] * (DIM - len(comps))


def _row(rid, vec, text="内容", page=3, doc=1, kb=1, enabled=True) -> VectorRow:
    return VectorRow(
        id=rid, vector=vec, chunk_text=text, page_number=page,
        doc_id=doc, kb_id=kb, enabled=enabled,
    )


def _mk_retriever(dim=DIM, *, rrf_k=60):
    """构造 HybridRetriever：FakeVector 稠密路 + BM25Index 稀疏路，同步插入数据。"""
    vector = FakeVector(dim=dim)
    bm25 = BM25Index()
    vector.ensure_collection()

    def _add(row: VectorRow) -> None:
        vector.insert([row])
        bm25.add(
            row.id, row.chunk_text,
            doc_id=row.doc_id, kb_id=row.kb_id,
            enabled=row.enabled, page_number=row.page_number,
        )

    return HybridRetriever(vector, bm25, rrf_k=rrf_k), _add


def test_rrf_merge_uses_rank_not_score():
    """两路分数差异巨大但 rank 相同时，融合结果一致——只认 rank 不认原始分。"""
    ret, add = _mk_retriever()
    # 稠密路：三个 chunk 与 Q 同向（COSINE 都≈1），rank 由稳定顺序决定
    # 稀疏路：查询词命中三个 chunk，但 BM25 分数因词频/长度不同而差异悬殊
    add(_row(1, _vec(1, 0), text="网络安全法 数据 保护", doc=11))
    add(_row(2, _vec(1, 0), text="数据 保护", doc=22))
    add(_row(3, _vec(1, 0), text="数据 保护 个人信息 数据 保护 数据 保护", doc=33))

    hits = ret.search("数据 保护", _vec(1, 0), kb_ids=[1], top_k=3)
    # 三个 chunk 在两路都被命中，source 均为 both（稠密 rank 相同 + 稀疏 rank 不同）
    assert len(hits) == 3
    assert all(h.source == "both" for h in hits)


def test_hybrid_respects_enabled_filter():
    """停用文档在两路都被排除，不进入融合。"""
    ret, add = _mk_retriever()
    add(_row(1, _vec(1, 0), text="网络安全法 数据 保护", doc=11, enabled=True))
    add(_row(2, _vec(1, 0), text="网络安全法 数据 保护", doc=22, enabled=False))  # 停用
    hits = ret.search("网络安全法 数据", _vec(1, 0), kb_ids=[1], top_k=5)
    assert [h.chunk_id for h in hits] == [1]  # 停用 doc=22 的 chunk 2 被排除


def test_source_flags_dense_sparse_both():
    """只有稠密命中 → dense；只有稀疏命中 → sparse；两路都命中 → both。"""
    ret, add = _mk_retriever()
    # chunk 1：向量同向（稠密命中），但文本不含查询词（稀疏不命中）
    add(_row(1, _vec(1, 0), text="完全无关的内容", doc=11))
    # chunk 2：向量正交（稠密分数 0，被 threshold 滤掉），但文本含查询词（稀疏命中）
    add(_row(2, _vec(0, 1), text="网络安全法 数据 保护", doc=22))
    # chunk 3：向量同向 + 文本含词（两路都命中）
    add(_row(3, _vec(1, 0), text="网络安全法 数据 保护", doc=33))

    # threshold=0.5 滤掉稠密路的正交向量（分数 0），chunk 2 仅稀疏路命中
    hits = ret.search("网络安全法 数据", _vec(1, 0), kb_ids=[1], top_k=3, threshold=0.5)
    by_id = {h.chunk_id: h.source for h in hits}
    assert by_id[3] == "both"
    assert by_id[1] == "dense"
    assert by_id[2] == "sparse"


def test_oversample_amplifies_top_k():
    """oversample 放大两路各自的 fetch_k，保证融合前有足够候选。"""
    ret, add = _mk_retriever()
    # 8 个 chunk：稠密路分数递减，稀疏路仅命中前 2 个
    for i in range(1, 9):
        angle = _vec(1.0 - i * 0.05, 0.1) if i < 8 else _vec(0, 1)
        text = "网络安全法 数据" if i <= 2 else f"无关内容 {i}"
        add(_row(i, angle, text=text, doc=10 + i))
    # top_k=2, oversample=4 → fetch_k=8，两路都能拿到全部候选再融合
    hits = ret.search("网络安全法 数据", _vec(1, 0), kb_ids=[1], top_k=2, oversample=4)
    assert len(hits) == 2


def test_hybrid_empty_kb_returns_empty():
    ret, add = _mk_retriever()
    assert ret.search("数据", _vec(1, 0), kb_ids=[]) == []
    assert ret.search("数据", _vec(1, 0), kb_ids=[1], top_k=5) == []


def test_bm25_index_scoring_prefers_rare_terms():
    """BM25 稀疏路：查询稀有词时，含该词的 chunk 排名更靠前（IDF 生效）。"""
    bm25 = BM25Index()
    bm25.add(1, "苹果 香蕉 橙子", doc_id=11, kb_id=1)
    bm25.add(2, "苹果 香蕉 橙子 网络安全法", doc_id=22, kb_id=1)  # 含稀有词
    hits = bm25.search("网络安全法", kb_ids=[1], top_k=5)
    assert [h.chunk_id for h in hits] == [2]  # 只有 chunk 2 命中稀有词
