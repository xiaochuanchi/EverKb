"""进程内后台 worker（Plan 1 Task 11）：守护线程轮询任务表。

单进程串行处理是计划设定（无分布式队列）：worker 循环调 run_pending，
interval 用 stop.wait 休眠（置位即醒，不硬睡）。生产由 lifespan 按
settings.worker_enabled 启动；测试可直接调 start_worker 传自己的 stop Event。

M3 生命周期（2026-11-20）：同线程追加每日一次的企业生命周期扫描（试用/服务
到期转冻结、到期前 7 天通知、冻结满 60 天清理），跨天触发，状态跃迁幂等。
"""
import logging
import threading
from datetime import date

from app.services.lifecycle import notify_expiring_soon, purge_expired, transition_expired
from app.services.pipeline import run_pending
from app.services.trace import Tracer

logger = logging.getLogger("everkb.worker")


def run_lifecycle_scan(session_factory, deps) -> None:
    """企业生命周期每日扫描：转冻结 → 提前通知 → 清理（顺序钉死，幂等）。

    转冻结（transition）在前、清理（purge）在后：当日刚转冻结的企业
    data_purge_at 必然在 60 天后，不会被同日清理误伤。清理注入 vector/
    storage/bm25 走删除红线顺序。
    """
    with session_factory() as session:
        transition_expired(session)
        notify_expiring_soon(session)
        purge_expired(
            session,
            vector=getattr(deps, "vector", None),
            storage=getattr(deps, "storage", None),
            bm25=getattr(deps, "bm25", None),
        )


def worker_loop(session_factory, deps, interval: float, stop: threading.Event) -> None:
    """处理循环：每轮调一次 run_pending，跨天调一次生命周期扫描，stop 置位即退。

    基础设施异常（MySQL 瞬断等）只记日志不退出——线程静默死亡 = 队列
    永久停摆（终审 Important #3）；下一轮轮询自愈。
    """
    # 管线观测 Tracer（二期 Task 29）：单实例可复用——process_document 内
    # 每次 start 新 trace_id 并 flush，观测写库失败被 Tracer 内部吞掉。
    tracer = Tracer()
    last_lifecycle_day: date | None = None
    while not stop.is_set():
        try:
            run_pending(
                session_factory,
                storage=deps.storage, embedder=deps.embedder,
                vector=deps.vector, settings=deps.settings,
                tracer=tracer, bm25=getattr(deps, "bm25", None),
            )
            # 每日一次生命周期扫描（跨天触发）
            today = date.today()
            if last_lifecycle_day != today:
                run_lifecycle_scan(session_factory, deps)
                last_lifecycle_day = today
        except Exception:
            logger.exception("worker 轮询失败，下一轮重试")
        stop.wait(interval)


def start_worker(
    session_factory, deps, interval: float, stop: threading.Event | None = None
) -> threading.Thread:
    """起守护线程 worker，返回线程对象；stop 供测试/优雅停机置位。"""
    stop = stop if stop is not None else threading.Event()
    thread = threading.Thread(
        target=worker_loop, args=(session_factory, deps, interval, stop),
        name="everkb-worker", daemon=True,
    )
    thread.start()
    return thread
