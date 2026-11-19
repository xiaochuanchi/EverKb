"""检索编排服务（Task 20）。

锁定点：
- retrieve：命中 chunk → 返回过滤后的 SearchHit；停用/删除 doc 被二次确认过滤；
  零命中返回空。
- build_context：chunk 正文 + 引用编号 [1][2] 拼上下文；citations 字段完整
  （doc_name/doc_id/chunk_id/page_number/snippet/score/source_url）。
"""
from decimal import Decimal

import pytest

from app.models import App, Document, RetrievalMode, SourceType
from app.services.embedding import FakeEmbedder
from app.services.rag import build_context, retrieve
from app.services.vector import FakeVector, SearchHit, VectorRow
from app.services.vector.hybrid_index import BM25IndexManager


def _make_app(*, kb_ids, top_k=5, score_threshold=None) -> App:
    return App(
        name="测试应用",
        kb_ids=kb_ids,
        api_key="sk-x",
        enabled=True,
        top_k=top_k,
        score_threshold=score_threshold,
    )


def _seed_doc(session, *, kb_id, name="文档A", enabled=True) -> Document:
    doc = Document(
        kb_id=kb_id,
        name=name,
        source_type=SourceType.UPLOAD,
        file_type="md",
        status=6,
        enabled=enabled,
    )
    session.add(doc)
    session.commit()
    session.refresh(doc)
    return doc


def _seed_hit(vector: FakeVector, *, chunk_id, doc_id, kb_id, text, score=0.9, page=None) -> None:
    vector.insert([
        VectorRow(
            id=chunk_id,
            vector=[1.0] * 8,
            chunk_text=text,
            page_number=page,
            doc_id=doc_id,
            kb_id=kb_id,
            enabled=True,
        )
    ])


def _query_vector(embedder) -> list[float]:
    """模拟编排层在 embedding span 内对问题 embed。"""
    return embedder.embed(["测试问题"])[0]


def test_retrieve_returns_hits_for_matching_kb(pipeline_env):
    """命中：问题 embed → 检索 → 二次确认 doc → 返回 SearchHit。"""
    vector = FakeVector(dim=8)
    embedder = FakeEmbedder(dim=8)
    session = pipeline_env.session

    doc = _seed_doc(session, kb_id=10)
    _seed_hit(vector, chunk_id=1, doc_id=doc.id, kb_id=10, text="产品说明内容")

    app = _make_app(kb_ids=[10], top_k=5)
    hits = retrieve(_query_vector(embedder), vector, session, app)
    assert len(hits) == 1
    assert hits[0].chunk_id == 1
    assert hits[0].doc_id == doc.id
    assert hits[0].chunk_text == "产品说明内容"


def test_retrieve_filters_disabled_doc(pipeline_env):
    """停用文档：向量命中但 doc.enabled=False → 二次确认过滤掉。"""
    vector = FakeVector(dim=8)
    embedder = FakeEmbedder(dim=8)
    session = pipeline_env.session

    doc = _seed_doc(session, kb_id=10, enabled=False)
    _seed_hit(vector, chunk_id=1, doc_id=doc.id, kb_id=10, text="停用内容")

    app = _make_app(kb_ids=[10])
    hits = retrieve(_query_vector(embedder), vector, session, app)
    assert hits == []


def test_retrieve_filters_deleted_doc(pipeline_env):
    """已删除文档（doc 行不存在）→ 过滤掉，不因孤儿向量命中而误引。"""
    vector = FakeVector(dim=8)
    embedder = FakeEmbedder(dim=8)
    session = pipeline_env.session

    _seed_hit(vector, chunk_id=99, doc_id=999999, kb_id=10, text="孤儿向量")

    app = _make_app(kb_ids=[10])
    hits = retrieve(_query_vector(embedder), vector, session, app)
    assert hits == []


def test_retrieve_zero_hit_returns_empty(pipeline_env):
    """无命中：空 kb 或阈值全滤 → 空列表。"""
    vector = FakeVector(dim=8)
    embedder = FakeEmbedder(dim=8)
    session = pipeline_env.session

    app = _make_app(kb_ids=[10])
    assert retrieve(_query_vector(embedder), vector, session, app) == []


def test_build_context_returns_numbered_context_and_citations(pipeline_env):
    """build_context：chunk 正文带 [1][2] 编号，citations 字段完整。"""
    session = pipeline_env.session
    doc = _seed_doc(session, kb_id=10, name="产品手册")
    doc.source_url = "https://example.com/manual"
    session.commit()

    hits = [
        SearchHit(chunk_id=1, doc_id=doc.id, kb_id=10, score=0.95,
                  chunk_text="这是第一段正文内容", page_number=3),
        SearchHit(chunk_id=2, doc_id=doc.id, kb_id=10, score=0.88,
                  chunk_text="这是第二段正文内容", page_number=5),
    ]
    context, citations = build_context(hits, [doc])

    assert "[1]" in context and "[2]" in context
    assert "这是第一段正文内容" in context
    assert "这是第二段正文内容" in context

    assert len(citations) == 2
    c1, c2 = citations
    assert c1["doc_name"] == "产品手册"
    assert c1["doc_id"] == doc.id
    assert c1["chunk_id"] == 1
    assert c1["page_number"] == 3
    assert c1["snippet"] == "这是第一段正文内容"
    assert c1["score"] == 0.95
    assert c1["source_url"] == "https://example.com/manual"
    assert c2["chunk_id"] == 2
    assert c2["score"] == 0.88


def test_build_context_empty_returns_empty(pipeline_env):
    """零命中：空上下文 + 空 citations。"""
    context, citations = build_context([], [])
    assert context == ""
    assert citations == []


def test_build_context_snippet_truncates_long_text(pipeline_env):
    """snippet 超长截断，避免大字段。"""
    session = pipeline_env.session
    doc = _seed_doc(session, kb_id=10, name="长文")

    long_text = "字" * 500
    hits = [SearchHit(chunk_id=1, doc_id=doc.id, kb_id=10, score=0.9,
                      chunk_text=long_text, page_number=None)]
    _, citations = build_context(hits, [doc])
    assert len(citations[0]["snippet"]) < 500


# ── 二期混合检索分流（Task 12）──────────────────────────────────


def _make_hybrid_app(*, kb_ids, top_k=5, mode=RetrievalMode.HYBRID) -> App:
    return App(
        name="混合检索应用",
        kb_ids=kb_ids,
        api_key="sk-x",
        enabled=True,
        top_k=top_k,
        retrieval_mode=mode,
    )


def test_retrieve_hybrid_mode_uses_bm25_and_vector(pipeline_env):
    """hybrid 模式：query 原文 + bm25 索引齐备时走混合检索，返回命中。"""
    vector = FakeVector(dim=8)
    embedder = FakeEmbedder(dim=8)
    session = pipeline_env.session

    doc = _seed_doc(session, kb_id=10)
    # 稠密路命中（向量同向）
    _seed_hit(vector, chunk_id=1, doc_id=doc.id, kb_id=10, text="网络安全法 数据 保护")
    # BM25 索引：同样文本可被关键词命中
    mgr = BM25IndexManager()
    from app.models import Chunk
    chunk = Chunk(id=1, document_id=doc.id, kb_id=10, chunk_index=0, content="网络安全法 数据 保护")
    mgr.add_chunk(chunk)

    app = _make_hybrid_app(kb_ids=[10])
    hits = retrieve(_query_vector(embedder), vector, session, app,
                    query="网络安全法 数据", bm25=mgr)
    assert len(hits) == 1
    assert hits[0].chunk_id == 1


def test_retrieve_hybrid_mode_falls_back_when_bm25_missing(pipeline_env):
    """hybrid 模式但 bm25/query 缺失 → 回退纯向量（不报错，向后兼容）。"""
    vector = FakeVector(dim=8)
    embedder = FakeEmbedder(dim=8)
    session = pipeline_env.session

    doc = _seed_doc(session, kb_id=10)
    _seed_hit(vector, chunk_id=1, doc_id=doc.id, kb_id=10, text="内容")

    app = _make_hybrid_app(kb_ids=[10], mode=RetrievalMode.HYBRID)
    # 不传 bm25/query → 回退 dense 路径
    hits = retrieve(_query_vector(embedder), vector, session, app)
    assert len(hits) == 1
    assert hits[0].chunk_id == 1


def test_retrieve_dense_mode_ignores_bm25(pipeline_env):
    """dense 模式：即使传入 bm25/query，仍走纯向量（模式优先）。"""
    vector = FakeVector(dim=8)
    embedder = FakeEmbedder(dim=8)
    session = pipeline_env.session

    doc = _seed_doc(session, kb_id=10)
    _seed_hit(vector, chunk_id=1, doc_id=doc.id, kb_id=10, text="内容")

    app = _make_hybrid_app(kb_ids=[10], mode=RetrievalMode.DENSE)
    hits = retrieve(_query_vector(embedder), vector, session, app,
                    query="内容", bm25=BM25IndexManager())
    assert len(hits) == 1
    assert hits[0].chunk_id == 1
