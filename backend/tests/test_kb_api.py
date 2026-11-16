"""知识库 CRUD API（Task 3）。

路由落在 /api/v1/admin/kbs：计划文档 Task 3 原文写 /api/kbs，技术决策记录
（2026-11-15）拍板管理流量统一挂 /api/v1/admin/ 前缀，冲突以决策记录为准。
"""
from app.models import Document, KBStatus

BASE = "/api/v1/admin/kbs"


def _create(client, name: str, **extra):
    return client.post(BASE, json={"name": name, **extra})


def test_create_kb_returns_201_with_id(client):
    r = _create(client, "产品手册", description="说明书库")
    assert r.status_code == 201
    body = r.json()
    assert body["id"] > 0
    assert body["name"] == "产品手册"
    assert body["description"] == "说明书库"
    assert body["status"] == KBStatus.ENABLED
    assert body["created_at"] is not None


def test_create_kb_description_defaults_empty(client):
    assert _create(client, "默认描述库").json()["description"] == ""


def test_create_duplicate_name_409(client):
    _create(client, "重名库")
    assert _create(client, "重名库").status_code == 409


def test_list_kbs(client):
    _create(client, "库一")
    _create(client, "库二")
    r = client.get(BASE)
    assert r.status_code == 200
    assert [kb["name"] for kb in r.json()] == ["库一", "库二"]


def test_patch_kb_status_to_disabled(client):
    kb_id = _create(client, "停用我").json()["id"]
    r = client.patch(f"{BASE}/{kb_id}", json={"status": KBStatus.DISABLED})
    assert r.status_code == 200
    assert r.json()["status"] == KBStatus.DISABLED


def test_patch_rename_to_taken_name_409(client):
    _create(client, "占名库")
    kb_id = _create(client, "改名库").json()["id"]
    r = client.patch(f"{BASE}/{kb_id}", json={"name": "占名库"})
    assert r.status_code == 409


def test_kb_not_found_404(client):
    assert client.patch(f"{BASE}/999", json={"status": 0}).status_code == 404
    assert client.delete(f"{BASE}/999").status_code == 404


def test_delete_empty_kb_204(client):
    kb_id = _create(client, "空库").json()["id"]
    assert client.delete(f"{BASE}/{kb_id}").status_code == 204


def test_delete_kb_with_document_409(client):
    kb_id = _create(client, "有文档库").json()["id"]
    session = client.app.state.session_factory()
    session.add(Document(kb_id=kb_id, name="doc.md"))
    session.commit()
    session.close()
    r = client.delete(f"{BASE}/{kb_id}")
    assert r.status_code == 409
