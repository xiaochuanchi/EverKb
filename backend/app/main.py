"""FastAPI 应用工厂（Plan 1 Task 1 Step 6 的接口约定）。

依赖注入缝：storage / embedder / vector 为 None 时按 settings 构造真实实现
（embedder/vector 的真实实现分别属 Task 8 / Task 9，当前挂 None 占位）。
测试路径：显式传入 LocalDiskStorage / Fake 双件套，绝不出网。
"""
from fastapi import FastAPI

from app.core.config import Settings, get_settings
from app.core.db import init_db, make_engine, make_session_factory
from app.core.storage import LocalDiskStorage, StorageClient


def create_app(
    settings: Settings | None = None,
    *,
    storage: StorageClient | None = None,
    embedder=None,
    vector=None,
) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="EverKB API", version="0.1.0")
    app.state.settings = settings

    # ── 基础设施 ────────────────────────────────────────────────
    engine = make_engine(settings.mysql_url)
    app.state.engine = engine
    app.state.session_factory = make_session_factory(engine)
    app.state.storage = storage if storage is not None else LocalDiskStorage(root=settings.storage_root)
    app.state.embedder = embedder  # None 占位：Task 8 接入 DashScope 真实实现
    app.state.vector = vector      # None 占位：Task 9 接入 Milvus 真实实现

    # 建表（一期无 Alembic：create_all，模型变更期删库重建）
    init_db(engine)

    # ── Worker（Task 11 实现后在此按 worker_enabled 启动守护线程）──
    # if settings.worker_enabled: start_worker(...)

    # ── 路由注册（Task 3 起逐步挂载 admin/open 两组）────────────
    # app.include_router(admin_router, prefix="/api/v1/admin")
    # app.include_router(open_router, prefix="/api/v1")

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
