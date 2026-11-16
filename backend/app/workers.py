"""进程内后台 worker（Plan 1 Task 11）：守护线程轮询任务表。

单进程串行处理是计划设定（无分布式队列）：worker 循环调 run_pending，
interval 用 stop.wait 休眠（置位即醒，不硬睡）。生产由 lifespan 按
settings.worker_enabled 启动；测试可直接调 start_worker 传自己的 stop Event。
"""
import logging
import threading

from app.services.pipeline import run_pending

logger = logging.getLogger("everkb.worker")


def worker_loop(session_factory, deps, interval: float, stop: threading.Event) -> None:
    """处理循环：每轮调一次 run_pending，stop 置位即退。

    基础设施异常（MySQL 瞬断等）只记日志不退出——线程静默死亡 = 队列
    永久停摆（终审 Important #3）；下一轮轮询自愈。
    """
    while not stop.is_set():
        try:
            run_pending(
                session_factory,
                storage=deps.storage, embedder=deps.embedder,
                vector=deps.vector, settings=deps.settings,
            )
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
