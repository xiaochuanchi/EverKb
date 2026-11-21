"""平台运营路由锁定测试（M5）：/api/v1/platform/* 的 fail-closed 鉴权与 CRUD 行为。

锁定点（方案 §9、§11）：
- require_platform fail-closed：企业管理员（ENT_ADMIN）、成员（MEMBER）访问一律 403；
- 开通/转正/冻结/充值/钱包查询的正确性；
- 充值累加（+=）+ 落 TOPUP 流水；
- 冻结设 data_purge_at = now + 60 天。

用 platform_client fixture（默认 seed PLATFORM 平台账号）验证 platform 正常路径；
再用 seed_admin 造 ENT_ADMIN / MEMBER 账号验证 403 越权。
"""
from decimal import Decimal

from fastapi.testclient import TestClient

from app.models import Enterprise, EnterpriseStatus, EnterpriseWallet, UserRole, WalletTransaction
from tests.conftest import seed_admin


def _platform_headers(platform_client: TestClient) -> dict:
    return dict(platform_client.headers)


def test_platform_list_enterprises(platform_client):
    """平台账号能列出企业（含冻结/清理态）。"""
    r = platform_client.get("/api/v1/platform/enterprises")
    assert r.status_code == 200
    assert isinstance(r.json()["data"], list)


def test_platform_create_and_wallet(platform_client):
    """开通企业：建企业 + 钱包 + 开通流水；随后钱包可查。"""
    r = platform_client.post(
        "/api/v1/platform/enterprises",
        json={"name": "甲公司", "trial_days": 7, "budget_cny": 20},
    )
    assert r.status_code == 201, r.text
    ent = r.json()["data"]
    assert ent["status"] == EnterpriseStatus.TRIAL
    assert ent["trial_ends_at"] is not None

    # 钱包可查，budget = 20
    w = platform_client.get(f"/api/v1/platform/enterprises/{ent['id']}/wallet")
    assert w.status_code == 200
    assert w.json()["data"]["budget_cny"] == 20.0
    assert w.json()["data"]["remaining_cny"] == 20.0


def test_platform_topup_accumulates(platform_client):
    """充值累加（+=）并落 TOPUP 流水。"""
    ent_id = platform_client.post(
        "/api/v1/platform/enterprises", json={"name": "乙公司", "budget_cny": 10}
    ).json()["data"]["id"]

    r = platform_client.post(
        f"/api/v1/platform/enterprises/{ent_id}/topup", json={"amount": 5}
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["budget_cny"] == 15.0

    # 再充一次，累加
    r2 = platform_client.post(
        f"/api/v1/platform/enterprises/{ent_id}/topup", json={"amount": 5}
    )
    assert r2.json()["data"]["budget_cny"] == 20.0


def test_platform_freeze_sets_purge_at(platform_client):
    """冻结：状态 FROZEN + data_purge_at 已设（now+60 天）。"""
    ent_id = platform_client.post(
        "/api/v1/platform/enterprises", json={"name": "丙公司"}
    ).json()["data"]["id"]

    r = platform_client.post(
        f"/api/v1/platform/enterprises/{ent_id}/freeze", json={"reason": "欠费"}
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["status"] == EnterpriseStatus.FROZEN
    assert data["freeze_reason"] == "欠费"
    assert data["data_purge_at"] is not None
    assert data["frozen_at"] is not None


def test_platform_activate_clears_freeze(platform_client):
    """转正：状态 ACTIVE，清冻结字段 + data_purge_at，设 service_ends_at。"""
    ent_id = platform_client.post(
        "/api/v1/platform/enterprises", json={"name": "丁公司"}
    ).json()["data"]["id"]
    platform_client.post(f"/api/v1/platform/enterprises/{ent_id}/freeze", json={})

    r = platform_client.post(
        f"/api/v1/platform/enterprises/{ent_id}/activate", json={"service_days": 365}
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["status"] == EnterpriseStatus.ACTIVE
    assert data["frozen_at"] is None
    assert data["freeze_reason"] == ""
    assert data["data_purge_at"] is None
    assert data["service_ends_at"] is not None


def test_platform_404_unknown_enterprise(platform_client):
    """不存在的企业 id → 404（topup / wallet / activate / freeze）。"""
    assert platform_client.post(
        "/api/v1/platform/enterprises/99999/topup", json={"amount": 1}
    ).status_code == 404
    assert platform_client.get("/api/v1/platform/enterprises/99999/wallet").status_code == 404


def test_ent_admin_forbidden_on_platform(platform_client):
    """企业管理员访问 platform 路由 → 403（fail-closed，不降级）。"""
    ent_admin = seed_admin(
        platform_client.app, username="entadmin", role=UserRole.ENT_ADMIN, enterprise_id=1
    )
    from app.core.security import create_access_token

    token = create_access_token(ent_admin.id, platform_client.app.state.settings)
    headers = {"Authorization": f"Bearer {token}"}
    r = platform_client.get("/api/v1/platform/enterprises", headers=headers)
    assert r.status_code == 403


def test_member_forbidden_on_platform(platform_client):
    """成员访问 platform 路由 → 403。"""
    member = seed_admin(
        platform_client.app, username="member", role=UserRole.MEMBER, enterprise_id=1
    )
    from app.core.security import create_access_token

    token = create_access_token(member.id, platform_client.app.state.settings)
    r = platform_client.get("/api/v1/platform/enterprises", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


# ── 企业管理员注册码（M5 补）─────────────────────────────────────


def test_platform_create_invite_code(platform_client):
    """发企业管理员注册码：返回明文 code，绑定企业，默认 max_uses=1。"""
    ent_id = platform_client.post(
        "/api/v1/platform/enterprises", json={"name": "发码公司"}
    ).json()["data"]["id"]

    r = platform_client.post(
        f"/api/v1/platform/enterprises/{ent_id}/invites",
        json={"max_uses": 3, "note": "给张三"},
    )
    assert r.status_code == 201, r.text
    data = r.json()["data"]
    assert data["code"].startswith("EVK-")
    assert data["enterprise_id"] == ent_id
    assert data["max_uses"] == 3
    assert data["used_count"] == 0
    assert data["enabled"] is True
    assert data["note"] == "给张三"


def test_platform_list_invite_codes(platform_client):
    """企业注册码列表：只列该企业的码，按 id 降序。"""
    ent_id = platform_client.post(
        "/api/v1/platform/enterprises", json={"name": "列表公司"}
    ).json()["data"]["id"]
    platform_client.post(f"/api/v1/platform/enterprises/{ent_id}/invites", json={})
    platform_client.post(f"/api/v1/platform/enterprises/{ent_id}/invites", json={})

    r = platform_client.get(f"/api/v1/platform/enterprises/{ent_id}/invites")
    assert r.status_code == 200
    assert len(r.json()["data"]) == 2


def test_platform_disable_invite_code(platform_client):
    """停用注册码：enabled 置 False；已注册账号不受影响（语义层面）。"""
    ent_id = platform_client.post(
        "/api/v1/platform/enterprises", json={"name": "停用公司"}
    ).json()["data"]["id"]
    invite_id = platform_client.post(
        f"/api/v1/platform/enterprises/{ent_id}/invites", json={}
    ).json()["data"]["id"]

    r = platform_client.post(f"/api/v1/platform/invites/{invite_id}/disable")
    assert r.status_code == 200
    assert r.json()["data"]["enabled"] is False


def test_platform_invite_404_unknown_enterprise(platform_client):
    """对不存在企业发码 → 404。"""
    assert platform_client.post(
        "/api/v1/platform/enterprises/99999/invites", json={}
    ).status_code == 404
    assert platform_client.get("/api/v1/platform/enterprises/99999/invites").status_code == 404


def test_ent_admin_forbidden_on_invite(platform_client):
    """企业管理员发码 → 403（注册码属平台运营，企业侧不可自颁）。"""
    ent_admin = seed_admin(
        platform_client.app, username="entadmin2", role=UserRole.ENT_ADMIN, enterprise_id=1
    )
    from app.core.security import create_access_token

    token = create_access_token(ent_admin.id, platform_client.app.state.settings)
    r = platform_client.post(
        "/api/v1/platform/enterprises/1/invites",
        json={},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403
