"""限流协议（Task 19）：chat 接口按 app_id 限流，防滥用。

抽象为 Protocol（与 embedder/vector 同构），测试注入内存 Fake 不触真 Redis；
真实实现 RedisRateLimiter 用固定窗口计数（Redis INCR + 首次 SETEX 过期）。
"""
from typing import Protocol


class RateLimiter(Protocol):
    """chat 限流器：同一 app_id 在窗口内调用次数是否放行。"""

    def allow(self, app_id: int) -> bool:
        """窗口内计数 +1；返回是否放行（True=放行，False=超限应 429）。"""
        ...
