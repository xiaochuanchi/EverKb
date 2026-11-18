"""X-API-Key 鉴权 + chat 限流（Task 19）。

直接测 deps.require_api_key / check_rate_limit 依赖函数——chat 端点（Task 21）
尚未实现，用探针路由挂依赖验证行为。锁定点：
- 无 key 401；错 key 401；停用应用 403；正确 key 通过；
- 限流超限 429。
"""
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.api.deps import check_rate_limit, require_api_key
from app.core.db import init_db, make_engine, make_session_factory
from app.models import App
from app.services.ratelimit import FakeRateLimiter


def _make_app():
    app = FastAPI()
    engine = make_engine("sqlite:///:memory:")
    init_db(engine)
    app.state.session_factory = make_session_factory(engine)
    app.state.rate_limiter = FakeRateLimiter()

    @app.get("/probe")
    def probe(app: App = Depends(require_api_key)):
        return {"app_id": app.id, "name": app.name}

    @app.get("/probe-limited")
    def probe_limited(app: App = Depends(check_rate_limit)):
        return {"app_id": app.id}

    return app


def _seed_app(app, *, name="测试应用", enabled=True, api_key="sk-test-key") -> App:
    with app.state.session_factory() as session:
        a = App(name=name, kb_ids=[], api_key=api_key, enabled=enabled)
        session.add(a)
        session.commit()
        session.refresh(a)
        return a


def test_no_api_key_401():
    app = _make_app()
    _seed_app(app)
    with TestClient(app) as c:
        r = c.get("/probe")  # 无头
        assert r.status_code == 401


def test_wrong_api_key_401():
    app = _make_app()
    _seed_app(app)
    with TestClient(app) as c:
        r = c.get("/probe", headers={"X-API-Key": "sk-wrong"})
        assert r.status_code == 401


def test_disabled_app_403():
    app = _make_app()
    _seed_app(app, enabled=False)
    with TestClient(app) as c:
        r = c.get("/probe", headers={"X-API-Key": "sk-test-key"})
        assert r.status_code == 403


def test_valid_api_key_passes():
    app = _make_app()
    a = _seed_app(app)
    with TestClient(app) as c:
        r = c.get("/probe", headers={"X-API-Key": "sk-test-key"})
        assert r.status_code == 200
        assert r.json() == {"app_id": a.id, "name": "测试应用"}


def test_rate_limit_429_when_exceeded():
    app = _make_app()
    a = _seed_app(app)
    # 阈值调到 3，便于测试
    app.state.rate_limiter.set_limit(3)
    with TestClient(app) as c:
        h = {"X-API-Key": "sk-test-key"}
        for _ in range(3):
            assert c.get("/probe-limited", headers=h).status_code == 200
        # 第 4 次超限
        assert c.get("/probe-limited", headers=h).status_code == 429


def test_rate_limit_per_app_isolated():
    """不同 app_id 的计数互不影响。"""
    app = _make_app()
    _seed_app(app, name="A")
    _seed_app(app, name="B", enabled=True, api_key="sk-key-b")
    app.state.rate_limiter.set_limit(1)
    with TestClient(app) as c:
        assert c.get("/probe-limited", headers={"X-API-Key": "sk-test-key"}).status_code == 200
        # A 超限，但 B 是独立窗口
        assert c.get("/probe-limited", headers={"X-API-Key": "sk-test-key"}).status_code == 429
        assert c.get("/probe-limited", headers={"X-API-Key": "sk-key-b"}).status_code == 200
