"""FakeRateLimiter：内存固定窗口计数（测试注入，不触真 Redis）。

与 RedisRateLimiter 同语义：每 app_id 独立窗口计数，超 limit 返回 False。
另暴露 set_limit 供测试把阈值调小，避免造 60 次调用。
"""
import time
from collections import defaultdict


class FakeRateLimiter:
    def __init__(self, *, limit: int = 60, window_sec: int = 60) -> None:
        self._limit = limit
        self._window_sec = window_sec
        self._counts: dict[int, list[float]] = defaultdict(list)

    def set_limit(self, limit: int) -> None:
        self._limit = limit

    def allow(self, app_id: int) -> bool:
        now = time.monotonic()
        # 剔除窗口外的旧调用
        self._counts[app_id] = [
            t for t in self._counts[app_id] if now - t < self._window_sec
        ]
        if len(self._counts[app_id]) >= self._limit:
            return False
        self._counts[app_id].append(now)
        return True
