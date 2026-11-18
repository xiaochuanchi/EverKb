"""RedisRateLimiter：固定窗口计数限流（Task 19）。

Redis 封装（技术决策记录 §3 接入点）于此落地最小面：chat 限流只需
INCR + EXPIRE 两个命令。key 形如 `chat_rate:{app_id}`，首次调用 SETEX
窗口（chat_rate_limit_per_min 秒），后续 INCR，超阈值返回 False。

限流器自身异常（Redis 不可达）按「限流不应阻断业务」原则放行（fail-open），
仅在日志留痕——避免中间件抖动把问答整条链路拖垮。
"""
import logging

import redis

logger = logging.getLogger(__name__)


class RedisRateLimiter:
    """固定窗口限流：Redis INCR + 首次 SETEX。"""

    def __init__(self, redis_url: str, *, limit: int = 60, window_sec: int = 60) -> None:
        self._client = redis.Redis.from_url(redis_url, decode_responses=True)
        self._limit = limit
        self._window_sec = window_sec

    def allow(self, app_id: int) -> bool:
        key = f"chat_rate:{app_id}"
        try:
            count = self._client.incr(key)
            if count == 1:  # 首次：设定窗口过期，否则 key 永存
                self._client.expire(key, self._window_sec)
            return count <= self._limit
        except redis.RedisError:
            logger.exception("rate limiter failed (fail-open), app_id=%s", app_id)
            return True
