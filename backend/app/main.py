"""FastAPI 应用工厂（Plan 1 Task 1 Step 6 的接口约定）。

依赖注入缝：storage / embedder / vector 为 None 时按 settings 构造真实实现。
构造时机在 lifespan（startup）而非 create_app 体内——MilvusClient(uri) 构造
即连接（死端口实测抛 MilvusException），模块级 app = create_app() 的 import
不能依赖外部服务存活。测试路径：显式传入 LocalDiskStorage / Fake 双件套，绝不出网。

lifespan（Task 11）：init_db → 补齐真实 embedder/vector → vector.ensure_collection
→ worker_enabled 时起 start_worker 守护线程。
"""
from contextlib import asynccontextmanager
from types import SimpleNamespace

from fastapi import FastAPI

from app.api.documents import router as documents_router
from app.api.kb import router as kb_router
from app.core.config import Settings, get_settings
from app.core.db import init_db, make_engine, make_session_factory
from app.core.storage import LocalDiskStorage, StorageClient
from app.services.embedding import create_embedder
from app.services.vector import create_vector
from app.workers import start_worker


@asynccontextmanager
async def lifespan(app: FastAPI):
    """startup：建表 → 未注入处补真实 embedder/vector → 确保向量 collection → 起 worker。"""
    init_db(app.state.engine)
    if app.state.embedder is None:
        app.state.embedder = create_embedder(app.state.settings)
    if app.state.vector is None:
        app.state.vector = create_vector(app.state.settings)
    app.state.vector.ensure_collection()
    if app.state.settings.worker_enabled:
        deps = SimpleNamespace(
            storage=app.state.storage,
            embedder=app.state.embedder,
            vector=app.state.vector,
            settings=app.state.settings,
        )
        start_worker(app.state.session_factory, deps, app.state.settings.worker_interval_sec)
    yield


def create_app(
    settings: Settings | None = None,
    *,
    storage: StorageClient | None = None,
    embedder=None,
    vector=None,
) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="EverKB API", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings

    # ── 基础设施 ────────────────────────────────────────────────
    engine = make_engine(settings.mysql_url)
    app.state.engine = engine
    app.state.session_factory = make_session_factory(engine)
    app.state.storage = storage if storage is not None else LocalDiskStorage(root=settings.storage_root)
    app.state.embedder = embedder  # None 时 lifespan 补真实实现（Task 8 DashScope 兼容端点）
    app.state.vector = vector      # None 时 lifespan 补真实实现（Task 9 Milvus）

    # ── 路由注册（Task 3 起逐步挂载 admin/open 两组）────────────
    # admin 侧统一挂 /api/v1/admin 前缀（技术决策记录：支撑部署层 IP 白名单）
    app.include_router(kb_router, prefix="/api/v1/admin")
    app.include_router(documents_router, prefix="/api/v1/admin")
    # app.include_router(open_router, prefix="/api/v1")

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
