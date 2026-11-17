"""API 统一信封（docs/2026-11-17-api统一信封-设计文档.md）。

Task 1 用 mini-app 钉包裹语义与异常映射；Task 2 追加真实接线契约测试。
红线 3：mini-app 不触网。
"""
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel
from fastapi.testclient import TestClient

from app.api.envelope import EnvelopeRoute, register_exception_handlers


def _mini_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)
    router = APIRouter(route_class=EnvelopeRoute)

    class Payload(BaseModel):
        name: str

    @router.post("/things", status_code=201)
    def create(payload: Payload) -> dict:
        return {"id": 1, "name": payload.name}

    @router.delete("/nothing")
    def nothing() -> None:
        return None

    @router.delete("/gone", status_code=204)
    def gone() -> None:
        return None

    @router.get("/raw", response_class=PlainTextResponse)
    def raw() -> str:
        return "ok"

    @router.get("/stream")
    def stream() -> StreamingResponse:
        return StreamingResponse(iter(["chunk1", "chunk2"]), media_type="text/plain")

    @router.get("/conflict")
    def conflict() -> dict:
        raise HTTPException(status_code=409, detail="知识库名已存在")

    @router.get("/auth")
    def auth() -> dict:
        raise HTTPException(status_code=401, detail="未登录", headers={"WWW-Authenticate": "Bearer"})

    @router.get("/boom")
    def boom() -> dict:
        raise RuntimeError("炸了")

    app.include_router(router)
    return app


def test_success_wraps_in_envelope():
    c = TestClient(_mini_app())
    r = c.post("/things", json={"name": "x"})
    assert r.status_code == 201
    assert r.json() == {"code": 0, "message": "ok", "data": {"id": 1, "name": "x"}}


def test_none_return_wraps_with_null_data():
    c = TestClient(_mini_app())
    r = c.delete("/nothing")
    assert r.status_code == 200
    assert r.json() == {"code": 0, "message": "ok", "data": None}


def test_non_json_response_passes_through():
    c = TestClient(_mini_app())
    r = c.get("/raw")
    assert r.status_code == 200
    assert r.text == "ok"  # 非 JSONResponse 原样放行，不包信封


def test_204_no_body_response_passes_through():
    c = TestClient(_mini_app())
    r = c.delete("/gone")
    assert r.status_code == 204
    assert r.text == ""  # 无体响应原样放行：非信封、status 204、不抛错


def test_streaming_response_passes_through():
    c = TestClient(_mini_app())
    r = c.get("/stream")
    assert r.status_code == 200
    assert r.text == "chunk1chunk2"  # 流式响应无 .body 属性，原样放行、非信封、不抛错


def test_http_exception_envelope():
    c = TestClient(_mini_app())
    r = c.get("/conflict")
    assert r.status_code == 409
    assert r.json() == {"code": 409, "message": "知识库名已存在", "data": None}


def test_http_exception_passes_headers():
    c = TestClient(_mini_app())
    r = c.get("/auth")
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"
    assert r.json()["message"] == "未登录"


def test_validation_error_envelope():
    c = TestClient(_mini_app())
    r = c.post("/things", json={})
    assert r.status_code == 422
    body = r.json()
    assert body["code"] == 422
    assert body["message"] == "参数校验失败"
    assert isinstance(body["data"], list)
    assert "loc" in body["data"][0] and "msg" in body["data"][0]


def test_unhandled_exception_returns_500_envelope():
    c = TestClient(_mini_app(), raise_server_exceptions=False)
    r = c.get("/boom")
    assert r.status_code == 500
    assert r.json() == {"code": 500, "message": "服务器内部错误", "data": None}


# ── 真实接线契约（Task 2）────────────────────────────────────────


def test_real_app_delete_returns_envelope(client):
    kb_id = client.post("/api/v1/admin/kbs", json={"name": "删除信封库"}).json()["data"]["id"]
    r = client.delete(f"/api/v1/admin/kbs/{kb_id}")
    assert r.status_code == 200
    assert r.json() == {"code": 0, "message": "ok", "data": None}


def test_route_not_found_envelope(client):
    """路由级 404（StarletteHTTPException）也走信封，不回落 {"detail": ...}。"""
    r = client.get("/api/v1/admin/nonexistent")
    assert r.status_code == 404
    assert r.json() == {"code": 404, "message": "Not Found", "data": None}


def test_health_stays_bare(client):
    """探活端点豁免信封（route_class 不得污染 /health）。"""
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_direct_constructed_route_envelopes():
    """裸构造 EnvelopeRoute(path, endpoint)（无 kwargs，钉住 __init__ 的
    response_class is None 缺省分支），注册进 mini-app 后成功响应同样包信封。
    starlette 1.10 的 Router 无 .add 方法，routes.append 即其注册机制
    （include_router 内部同款）。"""
    app = FastAPI()
    register_exception_handlers(app)

    def ping() -> dict:
        return {"pong": True}

    app.router.routes.append(EnvelopeRoute("/ping", ping))
    c = TestClient(app)
    r = c.get("/ping")
    assert r.status_code == 200
    assert r.json() == {"code": 0, "message": "ok", "data": {"pong": True}}
