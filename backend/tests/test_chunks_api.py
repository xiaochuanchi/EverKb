"""chunk 浏览 + 对账 API（Task 13）：分页/顺序/漂移检测。

红线 3：测试不触网——vector 用 FakeVector 注入，漂移通过直接操作 Fake 制造。
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models import Chunk, Document, DocumentStatus, KnowledgeBase
from app.services.vector.base import VectorRow


def _make_doc_with_chunks(app, *, n=3, status=DocumentStatus.COMPLETED, chunk_count=None) -> Document:
    """插 doc + n 条 chunk（vectorized=True）并同步写 FakeVector，形成对齐基线。

    返回 (doc, chunk_ids)。基线：MySQL chunk 数 == FakeVector 行数 == n，全 vectorized=True。
    """
    vector = app.state.vector
    with app.state.session_factory() as session:
        kb = KnowledgeBase(name="kb", enterprise_id=1)
        session.add(kb)
        session.flush()
        doc = Document(
            kb_id=kb.id,
            name="文档",
            source_type=1,
            file_type="docx",
            status=status,
            chunk_count=chunk_count if chunk_count is not None else n,
            enterprise_id=1,
        )
        session.add(doc)
        session.flush()
        chunk_ids = []
        for i in range(n):
            ch = Chunk(
                document_id=doc.id,
                kb_id=kb.id,
                chunk_index=i,
                content=f"第{i}块",
                token_count=len(f"第{i}块"),
                vectorized=True,
            )
            session.add(ch)
            session.flush()
            chunk_ids.append(ch.id)
            vector.insert([VectorRow(
                id=ch.id, vector=[0.0] * 8, chunk_text=ch.content,
                page_number=None, doc_id=doc.id, kb_id=kb.id, enabled=True,
            )])
        session.commit()
        session.refresh(doc)
        return doc, chunk_ids


def test_chunks_paginated_in_order(client: TestClient, tmp_path):
    app = client.app
    doc, _ = _make_doc_with_chunks(app, n=3)
    resp = client.get(f"/api/v1/admin/documents/{doc.id}/chunks", params={"page": 1, "size": 2})
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["total"] == 3
    assert [it["chunk_index"] for it in data["items"]] == [0, 1]
    assert data["items"][0]["vectorized"] is True
    assert data["items"][0]["content"] == "第0块"
    resp2 = client.get(f"/api/v1/admin/documents/{doc.id}/chunks", params={"page": 2, "size": 2})
    assert [it["chunk_index"] for it in resp2.json()["data"]["items"]] == [2]


def test_chunks_404_for_missing_doc(client: TestClient):
    resp = client.get("/api/v1/admin/documents/99999/chunks")
    assert resp.status_code == 404


def test_reconciliation_clean_when_aligned(client: TestClient):
    """对齐基线：status==6 且 vectorized 全 True 且计数一致 → 无异常。"""
    app = client.app
    doc, _ = _make_doc_with_chunks(app, n=2, status=DocumentStatus.COMPLETED)
    resp = client.get("/api/v1/admin/reconciliation")
    assert resp.status_code == 200
    items = resp.json()["data"]
    assert not any(it["doc_id"] == doc.id for it in items)


def test_reconciliation_detects_unvectorized(client: TestClient):
    app = client.app
    doc, chunk_ids = _make_doc_with_chunks(app, n=2, status=DocumentStatus.COMPLETED)
    # 制造漂移：把一条 chunk 的 vectorized 置 False（status==6 但存在未向量化 chunk）
    with app.state.session_factory() as session:
        chunk = session.scalar(select(Chunk).where(Chunk.document_id == doc.id).order_by(Chunk.chunk_index))
        chunk.vectorized = False
        session.commit()
    resp = client.get("/api/v1/admin/reconciliation")
    assert resp.status_code == 200
    items = resp.json()["data"]
    assert any(it["doc_id"] == doc.id and "unvectorized" in it["issue"] for it in items)


def test_reconciliation_detects_count_mismatch(client: TestClient):
    app = client.app
    doc, chunk_ids = _make_doc_with_chunks(app, n=3, status=DocumentStatus.COMPLETED)
    # 制造漂移：从 FakeVector 删一条（MySQL 3 条，向量只剩 2 条 → count_mismatch）
    app.state.vector.delete_by_ids([chunk_ids[0]])
    resp = client.get("/api/v1/admin/reconciliation")
    assert resp.status_code == 200
    items = resp.json()["data"]
    assert any(it["doc_id"] == doc.id and "count_mismatch" in it["issue"] for it in items)


def test_reconciliation_skips_incomplete_docs(client: TestClient):
    """未完成（status!=6）文档不参与对账——处理中天然 chunk 数与向量未对齐。"""
    app = client.app
    doc, _ = _make_doc_with_chunks(app, n=2, status=DocumentStatus.CHUNKED)
    resp = client.get("/api/v1/admin/reconciliation")
    assert resp.status_code == 200
    items = resp.json()["data"]
    assert not any(it["doc_id"] == doc.id for it in items)
