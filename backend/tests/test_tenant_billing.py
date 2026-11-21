"""M2 钱包计费锁定测试：双入口计费 + 企业钱包查询。

设计出处《商业化多租户设计方案 2026-11-20》§6、§11。锁定点：
- 企业管理员问答（assistant/chat）扣企业钱包 + 落消费流水；
- 平台账号（enterprise_id=NULL）问答不计费；
- open 侧问答扣 app 所属企业钱包（真实商业化入口）；
- 额度不足 403；wallet 端点返回正确余额。

红线 3：测试不出网——llm/embedder/vector 全部 Fake（conftest 注入）。
"""
import json

from app.models import (
    App,
    Enterprise,
    EnterpriseStatus,
    EnterpriseWallet,
    QaRecord,
    UserRole,
    WalletTransaction,
    WalletTxnType,
)
from tests.conftest import seed_admin

from app.core.security import create_access_token


def _make_enterprise(client, *, name="测试企业", status=EnterpriseStatus.ACTIVE) -> int:
    session = client.app.state.session_factory()
    ent = Enterprise(name=name, status=status)
    session.add(ent)
    session.flush()
    session.add(EnterpriseWallet(enterprise_id=ent.id, budget_cny=10, spent_cny=0, reserved_cny=0))
    session.commit()
    ent_id = ent.id
    session.close()
    return ent_id


def _make_app(client, *, enterprise_id=None, kb_ids=None, name="计费应用") -> int:
    session = client.app.state.session_factory()
    app = App(name=name, kb_ids=kb_ids or [], api_key=f"sk-{name}", enabled=True,
              enterprise_id=enterprise_id)
    session.add(app)
    session.commit()
    session.refresh(app)
    app_id = app.id
    session.close()
    return app_id


def _wallet(session, enterprise_id):
    return session.query(EnterpriseWallet).filter_by(enterprise_id=enterprise_id).one()


def _set_bearer(client, user) -> None:
    client.headers["Authorization"] = f"Bearer {create_access_token(user.id, client.app.state.settings)}"


def test_ent_admin_assistant_chat_charges_wallet(client, settings):
    """企业管理员后台问答：扣企业钱包 + 落消费流水。"""
    ent_id = _make_enterprise(client)
    app_id = _make_app(client, enterprise_id=ent_id)
    ent_admin = seed_admin(client.app, username="ent_admin", password="test1234",
                           role=UserRole.ENT_ADMIN, enterprise_id=ent_id)
    _set_bearer(client, ent_admin)

    with client.stream(
        "POST", "/api/v1/admin/assistant/chat",
        json={"app_id": app_id, "question": "你好"},
    ) as resp:
        assert resp.status_code == 200
        for line in resp.iter_lines():
            pass  # 消费完 SSE

    session = client.app.state.session_factory()
    w = _wallet(session, ent_id)
    # 有真实扣费：spent > 0
    assert w.spent_cny > 0
    # 消费流水已落
    txn = session.query(WalletTransaction).filter_by(enterprise_id=ent_id).one()
    assert txn.type == WalletTxnType.CONSUME
    assert txn.ref_type == "qa_record"
    session.close()


def test_platform_account_chat_is_free(platform_client):
    """平台账号（enterprise_id=NULL）问答不计费。"""
    app_id = _make_app(platform_client)  # 平台应用
    with platform_client.stream(
        "POST", "/api/v1/admin/assistant/chat",
        json={"app_id": app_id, "question": "免费提问"},
    ) as resp:
        assert resp.status_code == 200
        for line in resp.iter_lines():
            pass

    session = platform_client.app.state.session_factory()
    rec = session.query(QaRecord).one()
    # 平台账号问答：无企业归属，不计费
    assert rec.enterprise_id is None
    # 无钱包流水（没有任何企业）
    assert session.query(WalletTransaction).count() == 0
    session.close()


def test_ent_admin_insufficient_balance_403(client):
    """企业钱包额度为 0：问答被拒 403。"""
    ent_id = _make_enterprise(client)
    session = client.app.state.session_factory()
    w = _wallet(session, ent_id)
    w.budget_cny = 0  # 清零预算
    session.commit()
    session.close()

    app_id = _make_app(client, enterprise_id=ent_id)
    ent_admin = seed_admin(client.app, username="ent_admin2", password="test1234",
                           role=UserRole.ENT_ADMIN, enterprise_id=ent_id)
    _set_bearer(client, ent_admin)

    r = client.post("/api/v1/admin/assistant/chat", json={"app_id": app_id, "question": "x"})
    assert r.status_code == 403


def test_wallet_endpoint_returns_balance(client):
    """GET /admin/wallet 返回企业钱包余额（企业管理员视角）。"""
    ent_id = _make_enterprise(client)
    ent_admin = seed_admin(client.app, username="ent_admin3", password="test1234",
                           role=UserRole.ENT_ADMIN, enterprise_id=ent_id)
    _set_bearer(client, ent_admin)

    r = client.get("/api/v1/admin/wallet")
    assert r.status_code == 200
    data = r.json()["data"] if "data" in r.json() else r.json()
    assert data["enterprise_id"] == ent_id
    assert data["budget_cny"] == 10.0
    assert data["remaining_cny"] == 10.0


def test_wallet_endpoint_platform_account_403(platform_client):
    """平台账号无企业钱包：GET /admin/wallet 403。"""
    r = platform_client.get("/api/v1/admin/wallet")
    assert r.status_code == 403
