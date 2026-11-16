"""Vector 客户端（Task 9）：FakeVector 内存语义——检索过滤、删除、启停、计数。

红线 3：测试不触网——FakeVector 以余弦相似度模拟 Milvus COSINE 语义。
"""
import math

import pytest

from app.services.vector import FakeVector, SearchHit, VectorRow

DIM = 8
Q = [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]  # 查询向量恒为单位基向量


def _vec(*comps: float) -> list[float]:
    """前 len(comps) 维取给定值，其余补零——测试向量保持直观几何意义。"""
    return [float(c) for c in comps] + [0.0] * (DIM - len(comps))


def _row(rid, vec, text="内容", page=3, doc=1, kb=1, enabled=True) -> VectorRow:
    return VectorRow(
        id=rid, vector=vec, chunk_text=text, page_number=page,
        doc_id=doc, kb_id=kb, enabled=enabled,
    )


def test_search_hits_and_filters_by_kb_ids():
    v = FakeVector(dim=DIM)
    v.ensure_collection()
    v.insert([_row(1, _vec(1, 0), doc=11, kb=1), _row(2, _vec(1, 0), doc=22, kb=2)])
    hits = v.search(Q, kb_ids=[1], top_k=5)
    assert [h.chunk_id for h in hits] == [1]  # 只查指定 kb
    h = hits[0]
    assert isinstance(h, SearchHit)
    assert (h.doc_id, h.kb_id, h.chunk_text, h.page_number) == (11, 1, "内容", 3)
    assert h.score == pytest.approx(1.0)  # 同向单位向量 COSINE = 1


def test_search_orders_by_score_and_respects_top_k():
    v = FakeVector(dim=DIM)
    v.ensure_collection()
    # 三行与 Q 的夹角递增：1.0 / cos45 / 0.0
    v.insert([_row(1, _vec(1, 0)), _row(2, _vec(1, 1)), _row(3, _vec(0, 1))])
    hits = v.search(Q, kb_ids=[1], top_k=2)
    assert [h.chunk_id for h in hits] == [1, 2]  # 按分数降序取 top_k
    assert hits[0].score > hits[1].score >= hits[1].score
    assert hits[1].score == pytest.approx(math.cos(math.pi / 4))
    assert len(v.search(Q, kb_ids=[1], top_k=10)) == 3


def test_search_skips_disabled_rows():
    v = FakeVector(dim=DIM)
    v.ensure_collection()
    v.insert([_row(1, _vec(1, 0), enabled=False), _row(2, _vec(1, 0), enabled=True)])
    assert [h.chunk_id for h in v.search(Q, kb_ids=[1], top_k=5)] == [2]


def test_search_threshold_filters_low_scores():
    v = FakeVector(dim=DIM)
    v.ensure_collection()
    v.insert([_row(1, _vec(1, 0)), _row(2, _vec(0, 1))])  # 分数 1.0 / 0.0
    hits = v.search(Q, kb_ids=[1], top_k=5, threshold=0.5)
    assert [h.chunk_id for h in hits] == [1]  # 低于阈值的被滤掉
    assert len(v.search(Q, kb_ids=[1], top_k=5, threshold=None)) == 2


def test_delete_by_doc_removes_all_rows_of_doc():
    v = FakeVector(dim=DIM)
    v.ensure_collection()
    v.insert([_row(1, _vec(1, 0), doc=1), _row(2, _vec(1, 0), doc=1), _row(3, _vec(1, 0), doc=2, kb=2)])
    v.delete_by_doc(1)
    assert v.count_by_doc(1) == 0
    assert v.count_by_doc(2) == 1  # 其他 doc 不受影响


def test_delete_by_ids_removes_exact_rows():
    v = FakeVector(dim=DIM)
    v.ensure_collection()
    v.insert([_row(1, _vec(1, 0)), _row(2, _vec(1, 0)), _row(3, _vec(1, 0))])
    v.delete_by_ids([1, 3])
    assert [h.chunk_id for h in v.search(Q, kb_ids=[1], top_k=5)] == [2]
    v.delete_by_ids([])  # 空列表无操作不报错


def test_set_doc_enabled_toggles_visibility_only():
    v = FakeVector(dim=DIM)
    v.ensure_collection()
    v.insert([_row(1, _vec(1, 0), doc=7), _row(2, _vec(1, 0), doc=7)])
    v.set_doc_enabled(7, False)
    assert v.search(Q, kb_ids=[1], top_k=5) == []  # 不可见
    assert v.count_by_doc(7) == 2  # 行仍在（翻标志非删除）
    v.set_doc_enabled(7, True)
    assert [h.chunk_id for h in v.search(Q, kb_ids=[1], top_k=5)] == [1, 2]


def test_count_by_doc_counts_stored_rows():
    v = FakeVector(dim=DIM)
    v.ensure_collection()
    v.insert([_row(1, _vec(1, 0), doc=1), _row(2, _vec(1, 0), doc=1), _row(3, _vec(1, 0), doc=2, kb=2)])
    assert v.count_by_doc(1) == 2
    assert v.count_by_doc(2) == 1
    assert v.count_by_doc(9) == 0  # 不存在的 doc 计 0
