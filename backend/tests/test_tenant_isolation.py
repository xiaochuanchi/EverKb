"""数据级租户隔离锁定测试（M5 补：企业侧接口强制 enterprise_id 过滤）。

这是 M1「租户隔离」最关键一环的验收：此前企业侧接口（kb/documents/apps/
records/traces/notifications/dashboard/reconciliation/assistant）只挂了身份认证
（require_admin），没接 require_enterprise + scoped/ensure_owned，导致「企业 A
管理员能看到/操作企业 B 的数据」的越权漏洞（真实库暴露：admin1 属企业 2 却
看到企业 1 的遗留知识库/文档）。

锁定点：
- 列表接口：企业 A 只返回 enterprise_id==A 的数据，B 的数据不可见；
- 单对象接口：访问 B 的 kb/doc/app/record 一律 404（不泄露存在性）；
- 跨企业问答：企业 A 拿 B 的 app_id 问答 → 404；
- 建库/建应用自动挂当前企业 enterprise_id。

红线 3：全程 SQLite 内存库 + Fake，不触网。
"""
from app.models import (
    App,
    Document,
    DocumentStatus,
    Enterprise,
    EnterpriseStatus,
    KnowledgeBase,
    QaRecord,
    UserRole,
)
from tests.conftest import seed_admin


def _token(app, user):
    from app.core.security import create_access_token

    return {"Authorization": f"Bearer {create_access_token(user.id, app.state.settings)}"}


def _seed_two_enterprises(app):
    """企业 1 已由 conftest client fixture 造好；补企业 2 + 钱包。返回两企业 id。"""
    from app.models import EnterpriseWallet

    with app.state.session_factory() as s:
        e2 = Enterprise(id=2, name="企业B", status=EnterpriseStatus.ACTIVE)
        s.add(e2)
        s.flush()
        s.add(EnterpriseWallet(enterprise_id=2, budget_cny=1000, spent_cny=0, reserved_cny=0))
        s.commit()
    return 1, 2


def test_list_kbs_is_scoped_to_enterprise(client):
    """企业 A 管理员只能列出自己的知识库，看不到企业 B 的。"""
    _seed_two_enterprises(client.app)
    with client.app.state.session_factory() as s:
        s.add_all([
            KnowledgeBase(name="A的库", enterprise_id=1),
            KnowledgeBase(name="B的库", enterprise_id=2),
        ])
        s.commit()

    r = client.get("/api/v1/admin/kbs")
    assert r.status_code == 200
    names = [kb["name"] for kb in r.json()["data"]]
    assert names == ["A的库"]  # 只看到自己的


def test_get_cross_enterprise_kb_is_404(client):
    """企业 A 管理员访问企业 B 的知识库详情 → 404（不泄露存在性）。"""
    _seed_two_enterprises(client.app)
    with client.app.state.session_factory() as s:
        kb_b = KnowledgeBase(name="B的库", enterprise_id=2)
        s.add(kb_b)
        s.commit()
        s.refresh(kb_b)
        kb_b_id = kb_b.id

    assert client.patch(
        f"/api/v1/admin/kbs/{kb_b_id}", json={"description": "越权改"}
    ).status_code == 404
    assert client.delete(f"/api/v1/admin/kbs/{kb_b_id}").status_code == 404


def test_create_kb_sets_enterprise_id(client):
    """建库自动挂当前企业 enterprise_id（而不是 NULL）。"""
    _seed_two_enterprises(client.app)
    r = client.post("/api/v1/admin/kbs", json={"name": "新库"})
    assert r.status_code == 201
    with client.app.state.session_factory() as s:
        kb = s.query(KnowledgeBase).filter_by(name="新库").one()
        assert kb.enterprise_id == 1


def test_cross_enterprise_document_404(client):
    """企业 A 访问企业 B 的文档（详情/内容/chunk）→ 404。"""
    _seed_two_enterprises(client.app)
    with client.app.state.session_factory() as s:
        kb_b = KnowledgeBase(name="B的库", enterprise_id=2)
        s.add(kb_b)
        s.flush()
        doc_b = Document(kb_id=kb_b.id, name="B的文档", file_type="md", status=DocumentStatus.COMPLETED,
                         enterprise_id=2)
        s.add(doc_b)
        s.commit()
        s.refresh(doc_b)
        doc_b_id = doc_b.id

    assert client.get(f"/api/v1/admin/documents/{doc_b_id}").status_code == 404
    assert client.get(f"/api/v1/admin/documents/{doc_b_id}/chunks").status_code == 404


def test_list_apps_scoped(client):
    """企业 A 只能列出自己的应用。"""
    _seed_two_enterprises(client.app)
    with client.app.state.session_factory() as s:
        s.add_all([
            App(name="A应用", kb_ids=[], api_key="sk-a", enterprise_id=1),
            App(name="B应用", kb_ids=[], api_key="sk-b", enterprise_id=2),
        ])
        s.commit()

    r = client.get("/api/v1/admin/apps")
    names = [a["name"] for a in r.json()["data"]]
    assert names == ["A应用"]


def test_cross_enterprise_assistant_chat_404(client):
    """企业 A 拿企业 B 的 app_id 问答 → 404（应用归属校验）。"""
    _seed_two_enterprises(client.app)
    with client.app.state.session_factory() as s:
        app_b = App(name="B应用", kb_ids=[], api_key="sk-b", enterprise_id=2)
        s.add(app_b)
        s.commit()
        s.refresh(app_b)
        app_b_id = app_b.id

    r = client.post("/api/v1/admin/assistant/chat", json={"app_id": app_b_id, "question": "越权提问"})
    assert r.status_code == 404


def test_list_records_scoped(client):
    """企业 A 的问答记录只含自己的（B 的记录不可见）。"""
    _seed_two_enterprises(client.app)
    with client.app.state.session_factory() as s:
        s.add_all([
            QaRecord(app_id=1, enterprise_id=1, user_key="u", question="A问", answer="a", grounded=True),
            QaRecord(app_id=1, enterprise_id=2, user_key="u", question="B问", answer="a", grounded=True),
        ])
        s.commit()

    r = client.get("/api/v1/admin/records")
    assert r.status_code == 200
    items = r.json()["data"]["items"]
    assert [it["question"] for it in items] == ["A问"]


def test_platform_account_cannot_access_enterprise_route(platform_client):
    """平台账号（enterprise_id=None）访问企业侧接口 → 403（不降级）。"""
    assert platform_client.get("/api/v1/admin/kbs").status_code == 403
    assert platform_client.get("/api/v1/admin/apps").status_code == 403
    assert platform_client.get("/api/v1/admin/records").status_code == 403
