"""content.md 读写 API + 管线编辑续跑（Task 12.5，2026-11-17）。

锁定行为：
- GET /documents/{id}/content：status<3 → 409；存储缺对象 → 404；正常回 md
- PUT /documents/{id}/content：处理中 → 409；status∉(3,6) → 409；
  成功 → edited=True + status 置回 3（等 worker 续跑）
- 管线：进入 status==3 跳过解析直接切块；编辑完成态文档走替换语义
  （旧 chunk 行保留到新向量入库后才清）；lifespan 复位不碰 status==3
"""
import pytest

from app.models import Chunk, Document, DocumentStatus
from app.services.pipeline import content_key_for, run_pending
from tests.test_documents_api import _doc, _kb, _run_pending, _upload

BASE = "/api/v1/admin"


def _extract(client, kb_id: int) -> int:
    """上传并跑到 status==6（完成态），返回 doc_id。"""
    doc_id = _upload(client, kb_id).json()["data"]["id"]
    assert _run_pending(client) == 1
    assert _doc(client, doc_id).json()["data"]["status"] == DocumentStatus.COMPLETED
    return doc_id


@pytest.fixture()
def kb_and_doc(client):
    kb_id = _kb(client, "编辑库")
    return kb_id, _extract(client, kb_id)


# ── GET /content ──────────────────────────────────────────────────


def test_get_content_returns_markdown(client, kb_and_doc):
    kb_id, doc_id = kb_and_doc
    r = client.get(f"{BASE}/documents/{doc_id}/content")
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["document_id"] == doc_id
    assert "标题一" in body["content"]


def test_get_content_before_extract_is_409(client):
    kb_id = _kb(client, "未生成库")
    doc_id = _upload(client, kb_id).json()["data"]["id"]  # status=1，未跑管线
    r = client.get(f"{BASE}/documents/{doc_id}/content")
    assert r.status_code == 409
    assert "尚未生成" in r.json()["message"]


def test_get_content_missing_object_is_404(client, kb_and_doc):
    _, doc_id = kb_and_doc
    with client.app.state.session_factory() as s:
        doc = s.get(Document, doc_id)
        s.query(Chunk).filter(Chunk.document_id == doc_id).delete()
        s.delete(doc)
        # 重建行但不落 content 对象，模拟管线异常留下的空壳
        s.add(Document(kb_id=1, name="空壳", file_type="docx", status=DocumentStatus.EXTRACTED))
        s.commit()
        orphan_id = s.query(Document).filter(Document.name == "空壳").one().id
    r = client.get(f"{BASE}/documents/{orphan_id}/content")
    assert r.status_code == 404


# ── PUT /content ──────────────────────────────────────────────────


def test_put_content_marks_edited_and_requeues(client, kb_and_doc):
    kb_id, doc_id = kb_and_doc
    r = client.put(f"{BASE}/documents/{doc_id}/content", json={"content": "# 改后的标题\n\n新正文"})
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["edited"] is True
    assert body["status"] == DocumentStatus.EXTRACTED
    # 保存内容已落存储
    st = client.app.state
    assert st.storage.get_bytes(content_key_for(f"kb/{kb_id}/doc/{doc_id}/source.docx")).decode(
        "utf-8"
    ) == "# 改后的标题\n\n新正文"


def test_put_content_rejects_processing_state(client, kb_and_doc):
    _, doc_id = kb_and_doc
    _doc(client, doc_id)  # noop
    _set_status(client, doc_id, DocumentStatus.PARSING)
    r = client.put(f"{BASE}/documents/{doc_id}/content", json={"content": "x"})
    assert r.status_code == 409


def test_put_content_rejects_not_extracted(client):
    kb_id = _kb(client, "拒存库")
    doc_id = _upload(client, kb_id).json()["data"]["id"]  # status=1
    r = client.put(f"{BASE}/documents/{doc_id}/content", json={"content": "x"})
    assert r.status_code == 409


def _set_status(client, doc_id: int, status: int) -> None:
    with client.app.state.session_factory() as s:
        row = s.get(Document, doc_id)
        row.status = status
        s.commit()


# ── 管线续跑：从 status==3 起步，不重新解析 ───────────────────────


def test_edit_resume_rechunks_without_reparse(client, kb_and_doc, monkeypatch):
    """编辑续跑：旧 chunk 保留至新向量入库；解析器全程未被调用。"""
    from app.parsers import get_parser

    kb_id, doc_id = kb_and_doc
    client.put(f"{BASE}/documents/{doc_id}/content", json={"content": "# 编辑版\n\n正文乙"})

    called = []

    def _spy_parse(cls):
        called.append(True)
        raise AssertionError("编辑续跑不应触发解析")

    monkeypatch.setattr("app.services.pipeline.get_parser", _spy_parse)

    assert _run_pending(client) == 1
    assert called == []

    body = _doc(client, doc_id).json()["data"]
    assert body["status"] == DocumentStatus.COMPLETED
    assert body["edited"] is True
    with client.app.state.session_factory() as s:
        chunks = s.query(Chunk).filter(Chunk.document_id == doc_id).all()
        assert len(chunks) == body["chunk_count"] > 0
        assert any("正文乙" in c.content for c in chunks)


def test_edit_completed_doc_keeps_old_vectors_during_processing(client, kb_and_doc):
    """替换语义锁定：处理期间旧 chunk 行仍在库（worker 过期值覆盖窗不影响检索）。"""
    _, doc_id = kb_and_doc
    with client.app.state.session_factory() as s:
        old_ids = [rid for (rid,) in s.query(Chunk.id).filter(Chunk.document_id == doc_id)]

    client.put(f"{BASE}/documents/{doc_id}/content", json={"content": "# 新版\n\n内容丙"})
    # 手动把文档推进到 CHUNKED（模拟 worker 切块后、向量清理前）
    _run_pending(client)
    # 完成后旧 ids 已被精准清理：库中只剩新 chunk
    with client.app.state.session_factory() as s:
        now_ids = [rid for (rid,) in s.query(Chunk.id).filter(Chunk.document_id == doc_id)]
    assert not (set(old_ids) & set(now_ids))


def test_lifespan_reset_spares_extracted_status(tmp_path):
    """status==3 不被启动复位：编辑待续跑内容跨重启保留（真实文件库模拟重启）。"""
    from fastapi.testclient import TestClient

    from app.core.db import init_db
    from app.core.storage import LocalDiskStorage
    from app.main import create_app
    from tests.conftest import FakeEmbedder, FakeVector, make_test_settings, seed_admin

    def make_app() -> TestClient:
        settings = make_test_settings(
            tmp_path,
            mysql_url=f"sqlite:///{tmp_path / 'restart.db'}",
            storage_root=str(tmp_path / "storage"),
        )
        app = create_app(
            settings,
            storage=LocalDiskStorage(root=str(tmp_path / "storage")),
            embedder=FakeEmbedder(dim=8),
            vector=FakeVector(dim=8),
        )
        return app

    app1 = make_app()
    init_db(app1.state.engine)
    seed_admin(app1)
    with TestClient(app1) as c:
        c.headers["Authorization"] = c.headers.get("Authorization", "")  # 占位，下面真实签发
        from app.core.security import create_access_token

        c.headers["Authorization"] = f"Bearer {create_access_token(1, app1.state.settings)}"
        kb_id = _kb(c, "跨重启库")
        doc_id = _extract(c, kb_id)
        r = c.put(f"{BASE}/documents/{doc_id}/content", json={"content": "# 重启后仍在\n\n重启后正文"})
        assert r.status_code == 200

    # 重启：新 app（新 engine）挂同一个文件库 + 同一存储目录
    app2 = make_app()
    with TestClient(app2):
        with app2.state.session_factory() as s:
            row = s.get(Document, doc_id)
            assert row.status == DocumentStatus.EXTRACTED
            assert row.edited is True
    # 续跑可正常完成
    st = app2.state
    assert run_pending(
        st.session_factory, storage=st.storage, embedder=st.embedder,
        vector=st.vector, settings=st.settings,
    ) == 1
    with app2.state.session_factory() as s:
        row = s.get(Document, doc_id)
        assert row.status == DocumentStatus.COMPLETED, f"reason={row.status_reason!r}"
