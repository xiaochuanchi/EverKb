"""FastAPI 应用工厂（Plan 1 Task 1 Step 6 的接口约定）。

依赖注入缝：storage / embedder / vector 为 None 时按 settings 构造真实实现。
构造时机在 lifespan（startup）而非 create_app 体内——MilvusClient(uri) 构造
即连接（死端口实测抛 MilvusException），模块级 app = create_app() 的 import
不能依赖外部服务存活。测试路径：显式传入 LocalDiskStorage / Fake 双件套，绝不出网。

lifespan（Task 11）：init_db → 补齐真实 embedder/vector → vector.ensure_collection
→ worker_enabled 时起 start_worker 守护线程。
"""
import threading
from contextlib import asynccontextmanager
from types import SimpleNamespace

from fastapi import Depends, FastAPI
from fastapi.routing import APIRoute

from app.api.apps import router as apps_router
from app.api.assistant import router as assistant_router
from app.api.auth import require_admin, router as auth_router
from app.api.chunks import router as chunks_router
from app.api.dashboard import router as dashboard_router
from app.api.documents import router as documents_router
from app.api.envelope import register_exception_handlers
from app.api.evals import router as evals_router
from app.api.kb import router as kb_router
from app.api.notifications import router as notifications_router
from app.api.open import router as open_router
from app.api.reconciliation import router as reconciliation_router
from app.api.records import router as records_router
from app.api.traces import router as traces_router
from app.core.config import Settings, get_settings
from app.core.db import init_db, make_engine, make_session_factory
from app.core.storage import LocalDiskStorage, StorageClient
from app.models import Document, DocumentStatus
from app.services.embedding import create_embedder
from app.services.llm import create_llm
from app.services.ratelimit import FakeRateLimiter, RedisRateLimiter
from app.services.vector import create_vector
from app.services.vector.hybrid_index import BM25IndexManager
from app.workers import start_worker


@asynccontextmanager
async def lifespan(app: FastAPI):
    """startup：建表 → 复位卡死态 → 未注入处补真实 embedder/vector → 确保向量 collection → 起 worker。"""
    init_db(app.state.engine)
    # 进程可能死于处理中途（OOM/热重载）：2/4/5 是无主瞬态，复位为 1 恢复操作面
    # （spec §6.1「失败可重试」覆盖软异常，此处兜进程级中断；终审 Important #4）。
    # 3（EXTRACTED）不在复位列：content.md 已落存储，run_pending 会从切块阶段
    # 续跑——复位反而会把 md 编辑内容（PUT /content 置 3）重新解析覆盖。
    with app.state.session_factory() as session:
        session.query(Document).filter(Document.status.in_((
            DocumentStatus.PARSING,
            DocumentStatus.CHUNKED,
            DocumentStatus.VECTORIZING,
        ))).update(
            {
                Document.status: DocumentStatus.UPLOADED,
                Document.status_reason: "进程重启中断，自动重排",
            },
            synchronize_session=False,
        )
        session.commit()
    if app.state.embedder is None:
        app.state.embedder = create_embedder(app.state.settings)
    if app.state.vector is None:
        app.state.vector = create_vector(app.state.settings)
    if app.state.llm is None:
        app.state.llm = create_llm(app.state.settings)
    app.state.vector.ensure_collection()
    # 混合检索 BM25 索引：启动全量加载（未注入时构造；测试可注入自定义管理器）
    if app.state.bm25 is None:
        app.state.bm25 = BM25IndexManager()
    with app.state.session_factory() as session:
        loaded = app.state.bm25.load_from_db(session)
    logger = __import__("logging").getLogger("everkb")
    logger.info("BM25 索引已加载：%d chunk", loaded)
    worker_stop: threading.Event | None = None
    worker_thread: threading.Thread | None = None
    if app.state.settings.worker_enabled:
        deps = SimpleNamespace(
            storage=app.state.storage,
            embedder=app.state.embedder,
            vector=app.state.vector,
            settings=app.state.settings,
            bm25=app.state.bm25,
        )
        worker_stop = threading.Event()
        worker_thread = start_worker(
            app.state.session_factory, deps, app.state.settings.worker_interval_sec,
            stop=worker_stop,
        )
    yield
    # 优雅停机：置位 + join，缩短 worker 半途窗口（daemon 兜底仍在）
    if worker_stop is not None:
        worker_stop.set()
        worker_thread.join(timeout=5)


def create_app(
    settings: Settings | None = None,
    *,
    storage: StorageClient | None = None,
    embedder=None,
    vector=None,
    rate_limiter=None,
    llm=None,
    bm25=None,
) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="EverKB API", version="0.1.0", lifespan=lifespan)
    register_exception_handlers(app)  # 统一信封异常映射
    app.state.settings = settings

    # ── 基础设施 ────────────────────────────────────────────────
    engine = make_engine(settings.mysql_url)
    app.state.engine = engine
    app.state.session_factory = make_session_factory(engine)
    app.state.storage = storage if storage is not None else LocalDiskStorage(root=settings.storage_root)
    app.state.embedder = embedder  # None 时 lifespan 补真实实现（Task 8 DashScope 兼容端点）
    app.state.vector = vector      # None 时 lifespan 补真实实现（Task 9 Milvus）
    app.state.llm = llm            # None 时 lifespan 补真实实现（Task 16 LLM 客户端）
    app.state.bm25 = bm25          # None 时 lifespan 补真实实现（二期混合检索 BM25 索引）
    # 限流器：None 时按 redis_url 构造真实实现；测试注入 FakeRateLimiter（Task 19）
    if rate_limiter is not None:
        app.state.rate_limiter = rate_limiter
    elif settings.redis_url.startswith("redis://"):
        app.state.rate_limiter = RedisRateLimiter(
            settings.redis_url,
            limit=settings.chat_rate_limit_per_min,
        )
    else:
        # 非 redis 地址（如测试 SQLite 场景的缺省）→ 内存限流兜底，行为一致
        app.state.rate_limiter = FakeRateLimiter(limit=settings.chat_rate_limit_per_min)

    # ── 路由注册（Task 3 起逐步挂载 admin/open 两组）────────────
    # admin 侧统一挂 /api/v1/admin 前缀（技术决策记录：支撑部署层 IP 白名单）
    # 鉴权整包挂载（Task 14 / 计划 I8）：业务路由统一在此追加 require_admin，
    # 登录端点属 auth 路由包自身，不在此列。
    admin_auth = [Depends(require_admin)]
    app.include_router(auth_router, prefix="/api/v1/admin")
    app.include_router(kb_router, prefix="/api/v1/admin", dependencies=admin_auth)
    app.include_router(documents_router, prefix="/api/v1/admin", dependencies=admin_auth)
    app.include_router(chunks_router, prefix="/api/v1/admin", dependencies=admin_auth)
    app.include_router(reconciliation_router, prefix="/api/v1/admin", dependencies=admin_auth)
    app.include_router(apps_router, prefix="/api/v1/admin", dependencies=admin_auth)
    app.include_router(records_router, prefix="/api/v1/admin", dependencies=admin_auth)
    app.include_router(traces_router, prefix="/api/v1/admin", dependencies=admin_auth)
    app.include_router(evals_router, prefix="/api/v1/admin", dependencies=admin_auth)
    app.include_router(dashboard_router, prefix="/api/v1/admin", dependencies=admin_auth)
    app.include_router(assistant_router, prefix="/api/v1/admin", dependencies=admin_auth)
    app.include_router(notifications_router, prefix="/api/v1/admin", dependencies=admin_auth)
    app.include_router(open_router, prefix="/api/v1")
    _assert_admin_routes_protected(app)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    return app


def _assert_admin_routes_protected(app: FastAPI) -> None:
    """启动守卫：/api/v1/admin 下（auth 子树除外）路由漏挂 require_admin 即拒绝启动。

    新业务路由必须经 admin_auth 列表挂进 include_router，绕过它直接
    app.get(...) 写 admin 接口会在首次启动时炸出来。

    FastAPI 0.163 把 include_router 的路由包成 _IncludedRouter 惰性挂载
    （顶层 app.routes 看不到内层 APIRoute），故递归 include_context/original_router
    穿透；include 级 dependencies 与端点级 Depends 任一命中即视为已保护。
    """

    def _has_require_admin(deps) -> bool:
        # 端点级是 Dependant（.call）；include 级是原始 Depends（.dependency）
        for dep in deps:
            if getattr(dep, "call", None) is require_admin:
                return True
            if getattr(dep, "dependency", None) is require_admin:
                return True
        return False

    def _walk(routes, prefix: str, include_deps: tuple) -> None:
        for route in routes:
            if isinstance(route, APIRoute):
                full_path = prefix + route.path
                if not full_path.startswith("/api/v1/admin"):
                    continue
                if full_path.startswith("/api/v1/admin/auth/"):
                    continue  # auth 路由包自管（login 豁免、me/password 端点级挂载）
                if not _has_require_admin((*include_deps, *route.dependant.dependencies)):
                    raise RuntimeError(f"admin 路由漏挂鉴权: {route.methods} {full_path}")
                continue
            ctx = getattr(route, "include_context", None)
            original = getattr(route, "original_router", None)  # _IncludedRouter（0.163+）
            if ctx is not None and original is not None:
                _walk(original.routes, prefix + ctx.prefix, (*ctx.dependencies, *include_deps))
                continue
            inner = getattr(route, "routes", None)  # 普通嵌套 Router / APIRouter
            if inner is not None:
                _walk(inner, prefix, include_deps)

    _walk(app.routes, "", ())


app = create_app()
