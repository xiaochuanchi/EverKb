"""文档生命周期 API + 后台 worker（Task 11）。

路由落在 /api/v1/admin：Task 3 既有 ruling（管理流量统一前缀）。
红线 3：全程 Fake 双件套 + LocalDiskStorage，不触网。
"""
import threading
import time
from types import SimpleNamespace

import pytest

from fastapi.testclient import TestClient

from app.core.storage import LocalDiskStorage
from app.main import create_app
from app.models import Chunk, Document, DocumentStatus, SourceType
from app.services.embedding import FakeEmbedder
from app.services.pipeline import content_key_for, run_pending
from app.services.vector import FakeVector
from app.workers import start_worker
from tests.conftest import make_docx_bytes, make_test_settings

BASE = "/api/v1/admin"


def _kb(client, name: str = "文档库") -> int:
    return client.post(f"{BASE}/kbs", json={"name": name}).json()["id"]


def _upload(client, kb_id: int, filename: str = "测试.docx", data: bytes | None = None):
    if data is None:
        data = make_docx_bytes([("标题一", ["正文一段"])])
    return client.post(
        f"{BASE}/kbs/{kb_id}/documents",
        files={"file": (filename, data, "application/octet-stream")},
    )


def _web(client, kb_id: int, urls: list[str]):
    return client.post(f"{BASE}/kbs/{kb_id}/documents/web", json={"urls": urls})


def _doc(client, doc_id: int):
    return client.get(f"{BASE}/documents/{doc_id}")


def _set_status(client, doc_id: int, status: int, reason: str | None = None) -> None:
    """白盒置状态（Task 3 先例：手动造前置态）。"""
    with client.app.state.session_factory() as s:
        row = s.get(Document, doc_id)
        row.status = status
        row.status_reason = reason
        s.commit()


def _run_pending(client) -> int:
    st = client.app.state
    return run_pending(
        st.session_factory,
        storage=st.storage, embedder=st.embedder, vector=st.vector, settings=st.settings,
    )


# ── 注入缝与启动接线 ──────────────────────────────────────────────


def test_startup_keeps_injected_fakes(client):
    """lifespan 只对 None 补真实实现，显式注入的 Fake 原样保留（Plan 2 注入缝契约）。"""
    assert isinstance(client.app.state.vector, FakeVector)
    assert isinstance(client.app.state.embedder, FakeEmbedder)
    assert client.app.state.settings.worker_enabled is False  # 测试态不起 worker


# ── 上传 ─────────────────────────────────────────────────────────


def test_upload_docx_happy_path(client):
    kb_id = _kb(client)
    data = make_docx_bytes([("产品介绍", ["第一段", "第二段"])])
    r = _upload(client, kb_id, "产品手册.docx", data)
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == DocumentStatus.UPLOADED
    assert body["source_type"] == SourceType.UPLOAD
    assert body["version"] == 1
    assert body["file_size"] == len(data)
    assert body["file_type"] == "docx"
    # oss_key 按路径约定回填，且对象已落存储
    with client.app.state.session_factory() as s:
        doc = s.get(Document, body["id"])
        assert doc.oss_key == f"kb/{kb_id}/doc/{body['id']}/source.docx"
    client.app.state.storage.get_bytes(doc.oss_key)  # 不抛 FileNotFoundError 即存在


def test_upload_to_missing_kb_404(client):
    assert _upload(client, 999).status_code == 404


def test_upload_rejects_non_whitelisted_extension(client):
    kb_id = _kb(client)
    assert _upload(client, kb_id, "旧文档.doc", b"xx").status_code == 400
    assert _upload(client, kb_id, "无扩展名", b"xx").status_code == 400


def test_upload_oversize_413(tmp_path):
    settings = make_test_settings(tmp_path, upload_max_bytes=1000)
    app = create_app(
        settings,
        storage=LocalDiskStorage(root=str(tmp_path / "storage")),
        embedder=FakeEmbedder(dim=8),
        vector=FakeVector(dim=8),
    )
    with TestClient(app) as c:
        # 最小 docx（zip 容器开销）也远超 1000 字节上限
        r = _upload(c, _kb(c), "大文件.docx", make_docx_bytes([("标题", ["正文"])]))
        assert r.status_code == 413


# ── 网页批量添加 ─────────────────────────────────────────────────


def test_web_batch_creates_documents(client):
    kb_id = _kb(client)
    urls = ["https://example.com/a", "https://example.com/b"]
    r = _web(client, kb_id, urls)
    assert r.status_code == 201
    body = r.json()
    assert len(body) == 2
    for doc, url in zip(body, urls):
        assert doc["source_type"] == SourceType.WEBPAGE
        assert doc["source_url"] == url
        assert doc["status"] == DocumentStatus.UPLOADED
        assert doc["file_type"] == "html"
    with client.app.state.session_factory() as s:
        keys = [s.get(Document, d["id"]).oss_key for d in body]
    assert keys == [f"kb/{kb_id}/doc/{d['id']}/source.html" for d in body]


def test_web_batch_over_limit_422(client):
    kb_id = _kb(client)
    urls = [f"https://example.com/{i}" for i in range(51)]
    assert _web(client, kb_id, urls).status_code == 422


# ── 查询 ─────────────────────────────────────────────────────────


def test_get_document_and_404(client):
    doc_id = _upload(client, _kb(client)).json()["id"]
    assert _doc(client, doc_id).json()["id"] == doc_id
    assert _doc(client, 999).status_code == 404


def test_list_documents_filters_and_pagination(client):
    kb_id = _kb(client)
    ids = [_upload(client, kb_id).json()["id"] for _ in range(3)]
    _set_status(client, ids[0], DocumentStatus.FAILED, reason="解析失败")

    body = client.get(f"{BASE}/kbs/{kb_id}/documents").json()
    assert body["total"] == 3
    assert [d["id"] for d in body["items"]] == ids

    p1 = client.get(f"{BASE}/kbs/{kb_id}/documents", params={"page": 1, "size": 2}).json()
    p2 = client.get(f"{BASE}/kbs/{kb_id}/documents", params={"page": 2, "size": 2}).json()
    assert [d["id"] for d in p1["items"]] == ids[:2]
    assert [d["id"] for d in p2["items"]] == ids[2:]
    assert p2["total"] == 3

    failed = client.get(
        f"{BASE}/kbs/{kb_id}/documents", params={"status": DocumentStatus.FAILED}
    ).json()
    assert [d["id"] for d in failed["items"]] == [ids[0]]


# ── 重试 ─────────────────────────────────────────────────────────


def test_retry_failed_document(client):
    doc_id = _upload(client, _kb(client)).json()["id"]
    _set_status(client, doc_id, DocumentStatus.FAILED, reason="解析失败：疑似扫描件")
    r = client.post(f"{BASE}/documents/{doc_id}/retry")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == DocumentStatus.UPLOADED
    assert body["status_reason"] is None
    with client.app.state.session_factory() as s:
        assert s.get(Document, doc_id).status == DocumentStatus.UPLOADED


def test_retry_rejects_non_failed_and_missing(client):
    doc_id = _upload(client, _kb(client)).json()["id"]
    assert client.post(f"{BASE}/documents/{doc_id}/retry").status_code == 409  # status=1
    _set_status(client, doc_id, DocumentStatus.COMPLETED)
    assert client.post(f"{BASE}/documents/{doc_id}/retry").status_code == 409
    assert client.post(f"{BASE}/documents/999/retry").status_code == 404


# ── 启停 ─────────────────────────────────────────────────────────


def test_patch_enabled_syncs_vector(client):
    doc_id = _upload(client, _kb(client)).json()["id"]
    fake = client.app.state.vector
    r = client.patch(f"{BASE}/documents/{doc_id}/enabled", json={"enabled": False})
    assert r.status_code == 200
    assert r.json()["enabled"] is False
    assert fake.set_enabled_calls == [(doc_id, False)]
    with client.app.state.session_factory() as s:
        assert s.get(Document, doc_id).enabled is False
    assert client.patch(
        f"{BASE}/documents/{doc_id}/enabled", json={"enabled": True}
    ).json()["enabled"] is True
    assert fake.set_enabled_calls == [(doc_id, False), (doc_id, True)]
    assert client.patch(f"{BASE}/documents/999/enabled", json={"enabled": False}).status_code == 404


# ── 删除 ─────────────────────────────────────────────────────────


def test_delete_document_full_cleanup(client):
    kb_id = _kb(client)
    doc_id = _upload(client, kb_id).json()["id"]
    st = client.app.state
    assert _run_pending(client) == 1
    with st.session_factory() as s:
        oss_key = s.get(Document, doc_id).oss_key

    assert client.delete(f"{BASE}/documents/{doc_id}").status_code == 204
    assert doc_id in st.vector.deleted_doc_ids
    with st.session_factory() as s:
        assert s.query(Chunk).filter(Chunk.document_id == doc_id).count() == 0
        assert s.get(Document, doc_id) is None
    with pytest.raises(FileNotFoundError):
        st.storage.get_bytes(oss_key)
    with pytest.raises(FileNotFoundError):
        st.storage.get_bytes(content_key_for(oss_key))
    assert st.vector.count_by_doc(doc_id) == 0
    assert _doc(client, doc_id).status_code == 404
    assert client.delete(f"{BASE}/documents/{doc_id}").status_code == 404


def test_delete_document_removes_vectors_first(client):
    """红线 3：Milvus 先行——vector.delete_by_doc 触发时刻 MySQL chunk 行仍在。"""
    kb_id = _kb(client)
    doc_id = _upload(client, kb_id).json()["id"]
    st = client.app.state
    assert _run_pending(client) == 1

    seen = {}
    original = st.vector.delete_by_doc

    def spy(target_doc_id: int) -> None:
        with st.session_factory() as s:
            seen["chunk_rows_at_vector_delete"] = (
                s.query(Chunk).filter(Chunk.document_id == target_doc_id).count()
            )
        original(target_doc_id)

    st.vector.delete_by_doc = spy  # 实例属性覆盖（端点经 app.state.vector 取用）
    assert client.delete(f"{BASE}/documents/{doc_id}").status_code == 204
    assert seen["chunk_rows_at_vector_delete"] > 0


# ── 替换重传 ─────────────────────────────────────────────────────


def test_replace_put_file_keeps_old_content_md(client):
    kb_id = _kb(client)
    doc_id = _upload(
        client, kb_id, "第一版.docx", make_docx_bytes([("第一版标题", ["第一版正文"])])
    ).json()["id"]
    st = client.app.state
    assert _run_pending(client) == 1
    with st.session_factory() as s:
        oss_key = s.get(Document, doc_id).oss_key
    old_md = st.storage.get_bytes(content_key_for(oss_key))

    new_bytes = make_docx_bytes([("第二版标题", ["第二版正文", "补充内容"])])
    r = client.put(
        f"{BASE}/documents/{doc_id}/file",
        files={"file": ("第二版.docx", new_bytes, "application/octet-stream")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["version"] == 2
    assert body["status"] == DocumentStatus.UPLOADED
    assert st.storage.get_bytes(oss_key) == new_bytes  # source 已覆盖
    # 旧 content.md 未动：替换收尾（清旧 chunk）由管线成功后负责
    assert st.storage.get_bytes(content_key_for(oss_key)) == old_md


def test_replace_rejects_processing_state_and_webpage(client):
    kb_id = _kb(client)
    doc_id = _upload(client, kb_id).json()["id"]
    files = {"file": ("新.docx", make_docx_bytes([("t", ["x"])], ), "application/octet-stream")}
    _set_status(client, doc_id, DocumentStatus.CHUNKED)
    assert client.put(f"{BASE}/documents/{doc_id}/file", files=files).status_code == 409
    web_id = _web(client, kb_id, ["https://example.com/w"]).json()[0]["id"]
    assert client.put(f"{BASE}/documents/{web_id}/file", files=files).status_code == 409
    assert client.put(f"{BASE}/documents/999/file", files=files).status_code == 404


# ── worker 与队列处理 ────────────────────────────────────────────


def test_run_pending_processes_api_created_docs(client):
    kb_id = _kb(client)
    _upload(client, kb_id)
    _upload(client, kb_id)
    assert _run_pending(client) == 2
    with client.app.state.session_factory() as s:
        assert s.query(Document).filter(Document.status == DocumentStatus.COMPLETED).count() == 2


def test_worker_loop_processes_and_stops(client):
    doc_id = _upload(client, _kb(client)).json()["id"]
    st = client.app.state
    deps = SimpleNamespace(
        storage=st.storage, embedder=st.embedder, vector=st.vector, settings=st.settings
    )
    stop = threading.Event()
    t = start_worker(st.session_factory, deps, 0.02, stop=stop)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        with st.session_factory() as s:
            if s.get(Document, doc_id).status == DocumentStatus.COMPLETED:
                break
        time.sleep(0.02)
    with st.session_factory() as s:
        assert s.get(Document, doc_id).status == DocumentStatus.COMPLETED
    stop.set()
    t.join(timeout=2)
    assert not t.is_alive()
