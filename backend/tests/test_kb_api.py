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
    body = r.json()["data"]
    assert body["id"] > 0
    assert body["name"] == "产品手册"
    assert body["description"] == "说明书库"
    assert body["status"] == KBStatus.ENABLED
    assert body["created_at"] is not None


def test_create_kb_description_defaults_empty(client):
    assert _create(client, "默认描述库").json()["data"]["description"] == ""


def test_create_duplicate_name_409(client):
    _create(client, "重名库")
    assert _create(client, "重名库").status_code == 409


def test_list_kbs(client):
    _create(client, "库一")
    _create(client, "库二")
    r = client.get(BASE)
    assert r.status_code == 200
    assert [kb["name"] for kb in r.json()["data"]] == ["库一", "库二"]


def test_patch_kb_status_to_disabled(client):
    kb_id = _create(client, "停用我").json()["data"]["id"]
    r = client.patch(f"{BASE}/{kb_id}", json={"status": KBStatus.DISABLED})
    assert r.status_code == 200
    assert r.json()["data"]["status"] == KBStatus.DISABLED


def test_patch_rename_to_taken_name_409(client):
    _create(client, "占名库")
    kb_id = _create(client, "改名库").json()["data"]["id"]
    r = client.patch(f"{BASE}/{kb_id}", json={"name": "占名库"})
    assert r.status_code == 409


def test_kb_not_found_404(client):
    assert client.patch(f"{BASE}/999", json={"status": 0}).status_code == 404
    assert client.delete(f"{BASE}/999").status_code == 404


def test_delete_empty_kb_returns_envelope(client):
    kb_id = _create(client, "空库").json()["data"]["id"]
    r = client.delete(f"{BASE}/{kb_id}")
    assert r.status_code == 200
    assert r.json() == {"code": 0, "message": "ok", "data": None}


def test_delete_kb_with_document_409(client):
    kb_id = _create(client, "有文档库").json()["data"]["id"]
    session = client.app.state.session_factory()
    session.add(Document(kb_id=kb_id, name="doc.md"))
    session.commit()
    session.close()
    r = client.delete(f"{BASE}/{kb_id}")
    assert r.status_code == 409


# ── 评审修复回归（2026-11-16 review）──────────────────────────────


def test_patch_null_fields_are_ignored(client):
    """显式 null = 未提供（schemas.KBPatch 契约「未给的（None）不改」），返回 200 原值。"""
    kb_id = _create(client, "空值库", description="原描述").json()["data"]["id"]
    r = client.patch(f"{BASE}/{kb_id}", json={"name": None, "description": None, "status": None})
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["name"] == "空值库"
    assert body["description"] == "原描述"
    assert body["status"] == KBStatus.ENABLED


def test_create_name_race_maps_integrity_error_to_409(client, monkeypatch):
    """check-then-write 窗口的并发同名由唯一约束兜底：409 而非 500。

    单线程测试无法真实调度并发交错，用「已有同名行 + 预检查失明」等价制造
    竞态结果——IntegrityError 由真实唯一约束抛出，被测的是映射而非约束本身。
    """
    _create(client, "竞态库")
    monkeypatch.setattr("app.api.kb._name_taken", lambda *a, **k: False)
    r = client.post(BASE, json={"name": "竞态库"})
    assert r.status_code == 409


def test_patch_rename_race_maps_integrity_error_to_409(client, monkeypatch):
    """改名撞唯一约束（预检查窗口竞态）同样 409。"""
    kb_id = _create(client, "改名的库").json()["data"]["id"]
    _create(client, "被撞的库")
    monkeypatch.setattr("app.api.kb._name_taken", lambda *a, **k: False)
    r = client.patch(f"{BASE}/{kb_id}", json={"name": "被撞的库"})
    assert r.status_code == 409


# ── 终审 deferred minors 转正（2026-11-16）────────────────────────


def test_patch_status_out_of_domain_422(client):
    """status 域为 {0, 1}（KBStatus）：越域值 422，绝不静默落库。"""
    kb_id = _create(client, "限域库").json()["data"]["id"]
    r = client.patch(f"{BASE}/{kb_id}", json={"status": 42})
    assert r.status_code == 422


def test_create_name_validation_edges(client):
    """空名 / 超长名（>128）→ 422（pydantic 长度约束，锁定既有行为）。"""
    assert client.post(BASE, json={"name": ""}).status_code == 422
    assert client.post(BASE, json={"name": "字" * 129}).status_code == 422


def test_patch_rename_to_fresh_name_and_description(client):
    """正向路径：改名到新名 + 改描述均生效。"""
    kb_id = _create(client, "旧名库", description="旧描述").json()["data"]["id"]
    r = client.patch(f"{BASE}/{kb_id}", json={"name": "新名库", "description": "新描述"})
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["name"] == "新名库"
    assert body["description"] == "新描述"
