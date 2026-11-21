"""鉴权 API 行为锁定（Task 14）：login / me / password + 整包鉴权 + 启动守卫。

platform_client 夹具默认带已登录 token（conftest 预置 admin/test1234）；鉴权自身的
负向用例显式删除/覆盖该头。红线 3：全程 SQLite + Fake，不触网。
"""
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.api.auth import require_admin, router as auth_router
from app.api.envelope import EnvelopeRoute
from app.api.kb import router as kb_router
from app.core.security import create_access_token
from app.main import _assert_admin_routes_protected, create_app
from tests.conftest import TEST_ADMIN_PASSWORD, TEST_ADMIN_USERNAME, make_test_settings, seed_admin

BASE = "/api/v1/admin/auth"


def _login(platform_client, username=TEST_ADMIN_USERNAME, password=TEST_ADMIN_PASSWORD):
    return platform_client.post(f"{BASE}/login", json={"username": username, "password": password})


# ── 登录 ─────────────────────────────────────────────────────────


def test_login_success_returns_bearer_token(platform_client):
    r = _login(platform_client)
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["token_type"] == "bearer"
    assert data["access_token"]


def test_login_wrong_password_and_unknown_username_share_message(platform_client):
    """防账号枚举：两种失败同一措辞（决策锁定）。"""
    wrong_password = _login(platform_client, password="not-the-one").json()["message"]
    unknown_user = _login(platform_client, username="ghost").json()["message"]
    assert wrong_password == unknown_user == "用户名或密码错误"
    assert _login(platform_client, password="not-the-one").status_code == 401


def test_login_inactive_account_rejected(platform_client):
    seed_admin(platform_client.app, username="frozen", is_active=False)
    r = _login(platform_client, username="frozen")
    assert r.status_code == 401
    assert r.json()["message"] == "账号已禁用"


# ── 整包鉴权 ─────────────────────────────────────────────────────


def test_me_returns_current_user(platform_client):
    r = platform_client.get(f"{BASE}/me")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["username"] == TEST_ADMIN_USERNAME
    assert data["is_active"] is True
    assert "password_hash" not in data  # 敏感列绝不外发


def test_admin_route_without_token_is_401(platform_client):
    """业务路由整包挂 require_admin 的锁定：无头 → 401 + WWW-Authenticate。"""
    del platform_client.headers["Authorization"]
    r = platform_client.get("/api/v1/admin/kbs")
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"


def test_admin_route_with_garbage_token_is_401(platform_client):
    platform_client.headers["Authorization"] = "Bearer not-a-jwt"
    assert platform_client.get("/api/v1/admin/kbs").status_code == 401


def test_admin_route_with_expired_token_is_401(platform_client, tmp_path):
    """过期 token（exp 在过去）→ 401，由 require_admin 折叠 jwt 异常。"""
    expired = make_test_settings(tmp_path, jwt_expire_hours=-1)  # 同 jwt_secret="test"
    platform_client.headers["Authorization"] = f"Bearer {create_access_token(1, expired)}"
    assert platform_client.get("/api/v1/admin/kbs").status_code == 401


def test_login_endpoint_does_not_require_token(platform_client):
    """登录端点在 auth 子树内，无凭证可访问（整包鉴权豁免锁定）。"""
    del platform_client.headers["Authorization"]
    assert _login(platform_client).status_code == 200


# ── 改密码 ───────────────────────────────────────────────────────


def test_change_password_wrong_old_password_400(platform_client):
    r = platform_client.put(
        f"{BASE}/password",
        json={"old_password": "wrong-old", "new_password": "new-pass-99"},
    )
    assert r.status_code == 400
    assert r.json()["message"] == "原密码不正确"


def test_change_password_success_rotates_credentials(platform_client):
    r = platform_client.put(
        f"{BASE}/password",
        json={"old_password": TEST_ADMIN_PASSWORD, "new_password": "new-pass-99"},
    )
    assert r.status_code == 200
    # 旧密码立即失效，新密码可登录；新 token 可通过 /me
    assert _login(platform_client, password=TEST_ADMIN_PASSWORD).status_code == 401
    login = _login(platform_client, password="new-pass-99")
    assert login.status_code == 200
    me = platform_client.get(
        f"{BASE}/me",
        headers={"Authorization": f"Bearer {login.json()['data']['access_token']}"},
    )
    assert me.json()["data"]["username"] == TEST_ADMIN_USERNAME


def test_change_password_min_length_enforced_422(platform_client):
    r = platform_client.put(
        f"{BASE}/password",
        json={"old_password": TEST_ADMIN_PASSWORD, "new_password": "short"},
    )
    assert r.status_code == 422


# ── 启动守卫（计划 I8：漏挂的接口启动即报错）─────────────────────


def _bare_admin_app() -> FastAPI:
    app = FastAPI()
    app.include_router(auth_router, prefix="/api/v1/admin")
    return app


def test_startup_guard_rejects_unprotected_admin_route():
    """绕过整包挂载直接注册 admin 业务路由 → 启动守卫拒绝启动。"""
    app = _bare_admin_app()

    @app.get("/api/v1/admin/evil")
    def evil() -> dict:  # 忘了挂 require_admin 的写法
        return {"leak": True}

    with pytest.raises(RuntimeError, match="漏挂鉴权"):
        _assert_admin_routes_protected(app)


def test_startup_guard_rejects_unprotected_included_router():
    """include_router 漏挂 dependencies（FastAPI 0.163 _IncludedRouter 惰性挂载）
    → 启动守卫同样拒绝。锁定 2026-11-17 发现的守卫穿透盲区。"""
    from fastapi import APIRouter

    app = FastAPI()
    router = APIRouter(route_class=EnvelopeRoute)

    @router.get("/kbs2")
    def kbs2() -> dict:
        return {"unprotected": True}

    app.include_router(router, prefix="/api/v1/admin")  # 忘了 dependencies=[...]
    with pytest.raises(RuntimeError, match="漏挂鉴权"):
        _assert_admin_routes_protected(app)


def test_startup_guard_ignores_auth_subtree_and_protected_routes():
    app = _bare_admin_app()
    app.include_router(kb_router, prefix="/api/v1/admin", dependencies=[Depends(require_admin)])
    _assert_admin_routes_protected(app)  # 不抛即通过


def test_create_app_mounts_everything_protected(settings, tmp_path):
    """真实 create_app 路径：守卫通过（auth 豁免 + kb/documents 均已挂）。"""
    from app.core.storage import LocalDiskStorage
    from app.services.embedding import FakeEmbedder
    from app.services.vector import FakeVector

    app = create_app(
        make_test_settings(tmp_path),
        storage=LocalDiskStorage(root=str(tmp_path / "storage")),
        embedder=FakeEmbedder(dim=8),
        vector=FakeVector(dim=8),
    )
    # create_app 内部已调用守卫，走到这里即通过
    assert app.title == "EverKB API"
