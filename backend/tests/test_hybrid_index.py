"""BM25 索引管理器（二期混合检索接入生产）。

锁定点：
- load_from_db：从 MySQL 全量加载 enabled 文档的 chunk，停用文档不载入；
- add_chunk / delete_by_doc / delete_by_ids / set_doc_enabled 增量同步后，
  检索结果与 MySQL/Milvus 一致（不漂移）；
- search 透传 BM25 分数，停用 chunk 与 kb 外 chunk 不命中。
"""
from app.models import Chunk, Document, SourceType
from app.services.vector.hybrid_index import BM25IndexManager


def _seed_doc(session, *, kb_id, name="文档A", enabled=True) -> Document:
    doc = Document(
        kb_id=kb_id, name=name, source_type=SourceType.UPLOAD,
        file_type="md", status=6, enabled=enabled,
    )
    session.add(doc)
    session.commit()
    session.refresh(doc)
    return doc


def _seed_chunk(session, *, doc_id, kb_id, idx, content) -> Chunk:
    c = Chunk(
        document_id=doc_id, kb_id=kb_id, chunk_index=idx,
        content=content, token_count=len(content), vectorized=True,
    )
    session.add(c)
    session.commit()
    session.refresh(c)
    return c


def test_load_from_db_indexes_enabled_chunks(pipeline_env):
    """全量加载：enabled 文档的 chunk 载入，停用文档不载入。"""
    session = pipeline_env.session
    doc_on = _seed_doc(session, kb_id=1)
    doc_off = _seed_doc(session, kb_id=1, enabled=False)
    _seed_chunk(session, doc_id=doc_on.id, kb_id=1, idx=0, content="网络安全法 数据 保护")
    _seed_chunk(session, doc_id=doc_off.id, kb_id=1, idx=0, content="停用文档的内容")

    mgr = BM25IndexManager()
    n = mgr.load_from_db(session)
    assert n == 1  # 只加载 enabled 文档的 chunk

    hits = mgr.search("网络安全法", [1], top_k=5)
    assert len(hits) == 1
    assert hits[0].doc_id == doc_on.id


def test_load_from_db_idempotent_reload(pipeline_env):
    """重复加载：幂等重载，不累积重复。"""
    session = pipeline_env.session
    doc = _seed_doc(session, kb_id=1)
    _seed_chunk(session, doc_id=doc.id, kb_id=1, idx=0, content="内容一")

    mgr = BM25IndexManager()
    mgr.load_from_db(session)
    mgr.load_from_db(session)  # 二次加载
    assert mgr.size() == 1


def test_incremental_add_and_search(pipeline_env):
    """增量 add：加载后新增 chunk 可被检索。"""
    session = pipeline_env.session
    doc = _seed_doc(session, kb_id=1)
    mgr = BM25IndexManager()
    mgr.load_from_db(session)

    c = _seed_chunk(session, doc_id=doc.id, kb_id=1, idx=1, content="新增的关键词内容")
    mgr.add_chunk(c)

    hits = mgr.search("关键词", [1], top_k=5)
    assert any(h.chunk_id == c.id for h in hits)


def test_incremental_delete_by_doc(pipeline_env):
    """增量 delete_by_doc：删除后不再命中。"""
    session = pipeline_env.session
    doc = _seed_doc(session, kb_id=1)
    _seed_chunk(session, doc_id=doc.id, kb_id=1, idx=0, content="待删除内容")
    mgr = BM25IndexManager()
    mgr.load_from_db(session)
    assert len(mgr.search("待删除", [1], top_k=5)) == 1

    mgr.delete_by_doc(doc.id)
    assert mgr.search("待删除", [1], top_k=5) == []


def test_set_doc_enabled_filters_search(pipeline_env):
    """停用后不参与检索；启用后恢复。"""
    session = pipeline_env.session
    doc = _seed_doc(session, kb_id=1)
    _seed_chunk(session, doc_id=doc.id, kb_id=1, idx=0, content="停用启用内容")
    mgr = BM25IndexManager()
    mgr.load_from_db(session)
    assert len(mgr.search("停用启用", [1], top_k=5)) == 1

    mgr.set_doc_enabled(doc.id, False)
    assert mgr.search("停用启用", [1], top_k=5) == []

    mgr.set_doc_enabled(doc.id, True)
    assert len(mgr.search("停用启用", [1], top_k=5)) == 1


def test_search_filters_out_of_kb(pipeline_env):
    """kb 外 chunk 不命中。"""
    session = pipeline_env.session
    doc = _seed_doc(session, kb_id=1)
    _seed_chunk(session, doc_id=doc.id, kb_id=1, idx=0, content="kb1 的内容")
    mgr = BM25IndexManager()
    mgr.load_from_db(session)

    assert mgr.search("内容", [2], top_k=5) == []  # 查 kb 2，但索引只有 kb 1
