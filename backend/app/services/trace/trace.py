"""Trace 服务：一次问答的 Span 记录器（内存暂存，流结束后批量落库）。

纪律（models.py 四次修订 10）：
- 时长用单调钟测（time.monotonic）、时刻用墙钟记（datetime.now）；
- 流结束后批量落库；
- 观测写库失败 try/except 包死，绝不打断问答。

设计：
- Tracer.start(trace_id) 开启一次问答的 span 收集；
- Tracer.span(name, span_type, parent_id=None) 返回 SpanContext（上下文管理器）；
- SpanContext 的 parent_id 传「内存 span_id」，flush 时映射为真实 DB 主键；
- Tracer.flush(session) 批量 insert，异常吞掉并 log，幂等（只 flush 一次）。
"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from decimal import Decimal
from typing import Optional

from app.models import TraceSpan

logger = logging.getLogger(__name__)


class SpanContext:
    """单个 span 的上下文管理器：__enter__ 记 start，__exit__ 记 end 与 latency_ms。

    可选的 setter（set_input_summary / set_output_summary / set_tokens / set_cost）
    在 span 存活期间调用；未调用的字段落库为 NULL，由模型默认值兜底。
    """

    def __init__(self, tracer: "Tracer", name: str, span_type: str, parent_id: Optional[int]):
        self._tracer = tracer
        self.name = name
        self.span_type = span_type
        self._parent_mem_id = parent_id
        self.span_id: int = tracer._next_span_id()

        # 记录数据
        self.input_summary: Optional[str] = None
        self.output_summary: Optional[str] = None
        self.tokens_in: Optional[int] = None
        self.tokens_out: Optional[int] = None
        self.cost: Optional[Decimal] = None

        # 时间（单调钟测时长，墙钟记时刻）
        self._start_mono: Optional[float] = None
        self._start_wall: Optional[datetime] = None
        self._end_wall: Optional[datetime] = None
        self.latency_ms: int = 0

    def __enter__(self) -> "SpanContext":
        self._start_mono = time.monotonic()
        self._start_wall = datetime.now()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self._end_wall = datetime.now()
        if self._start_mono is not None:
            self.latency_ms = int((time.monotonic() - self._start_mono) * 1000)
        # 结束即登记进 tracer，等待批量 flush
        self._tracer._record(self)

    # ── setter ──────────────────────────────────────────────
    def set_input_summary(self, text: str) -> None:
        self.input_summary = text

    def set_output_summary(self, text: str) -> None:
        self.output_summary = text

    def set_tokens(self, *, in_tokens: int, out_tokens: int) -> None:
        self.tokens_in = in_tokens
        self.tokens_out = out_tokens

    def set_cost(self, cost: Decimal) -> None:
        self.cost = cost


class Tracer:
    """一次问答的 span 记录器。"""

    def __init__(self) -> None:
        self._trace_id: Optional[int] = None
        self._spans: list[SpanContext] = []
        self._flushed = False
        self._mem_counter = 0

    def start(self, trace_id: int) -> None:
        self._trace_id = trace_id
        self._spans = []
        self._flushed = False
        self._mem_counter = 0

    def _next_span_id(self) -> int:
        self._mem_counter += 1
        return self._mem_counter

    def span(self, name: str, span_type: str, *, parent_id: Optional[int] = None) -> SpanContext:
        return SpanContext(self, name, span_type, parent_id)

    def _record(self, span: SpanContext) -> None:
        self._spans.append(span)

    def flush(self, session) -> None:
        """批量落库全部 span。幂等、异常吞掉不抛（观测失败绝不打断问答）。"""
        if self._flushed or self._trace_id is None:
            return
        if not self._spans:
            self._flushed = True
            return
        try:
            # 内存 span_id → 真实 DB 主键映射（parent_span_id 需要）
            mem_to_db: dict[int, int] = {}
            rows: list[TraceSpan] = []
            for s in self._spans:
                row = TraceSpan(
                    trace_id=self._trace_id,
                    parent_span_id=None,
                    name=s.name,
                    span_type=s.span_type,
                    input_summary=s.input_summary,
                    output_summary=s.output_summary,
                    start_time=s._start_wall,
                    end_time=s._end_wall,
                    latency_ms=s.latency_ms,
                    gen_ai_usage_tokens_in=s.tokens_in,
                    gen_ai_usage_tokens_out=s.tokens_out,
                    cost=s.cost,
                )
                session.add(row)
                session.flush()  # 回填 row.id
                mem_to_db[s.span_id] = row.id
                rows.append(row)
            # 回填 parent_span_id（此时所有真实 id 已就绪）
            for s, row in zip(self._spans, rows):
                if s._parent_mem_id is not None:
                    row.parent_span_id = mem_to_db.get(s._parent_mem_id)
            self._flushed = True
        except Exception:  # noqa: BLE001 —— 观测写库失败必须吞掉，不打断主流程
            logger.exception("trace flush failed (trace_id=%s), ignored", self._trace_id)
            self._flushed = True
