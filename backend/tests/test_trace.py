"""Trace 服务（Tracer + SpanContext）测试。

锁定点（models.py 四次修订 10 的纪律）：
- 时长用单调钟测、时刻用墙钟记；
- 流结束后批量落库；
- 观测写库失败 try/except 包死，绝不打断问答。
"""
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import TraceSpan
from app.services.trace import Tracer


def _flush_tracer(tracer: Tracer, session) -> None:
    tracer.flush(session)
    session.commit()


def test_tracer_records_flat_spans(pipeline_env):
    """无嵌套：start 后 span 两次，flush 后库中两条 span，latency_ms 非负、字段完整。"""
    tracer = Tracer()
    tracer.start(trace_id=1)

    with tracer.span("gen_ai.embedding", "embedding") as s1:
        s1.set_input_summary("问题文本")
        s1.set_output_summary("1024 维向量")
        s1.set_tokens(in_tokens=10, out_tokens=0)

    with tracer.span("milvus.search", "retrieval") as s2:
        s2.set_cost(Decimal("0.0001"))

    _flush_tracer(tracer, pipeline_env.session)

    spans = list(
        pipeline_env.session.scalars(
            select(TraceSpan).where(TraceSpan.trace_id == 1).order_by(TraceSpan.id)
        )
    )
    assert len(spans) == 2
    assert [s.name for s in spans] == ["gen_ai.embedding", "milvus.search"]
    assert [s.span_type for s in spans] == ["embedding", "retrieval"]
    for s in spans:
        assert s.parent_span_id is None
        assert s.latency_ms >= 0
        assert s.start_time is not None
        assert s.end_time is not None
        assert s.end_time >= s.start_time
    assert spans[0].input_summary == "问题文本"
    assert spans[0].gen_ai_usage_tokens_in == 10
    assert spans[0].gen_ai_usage_tokens_out == 0
    assert spans[1].cost == Decimal("0.0001")


def test_tracer_nested_spans_form_tree(pipeline_env):
    """嵌套 span：parent_id 正确成链，parent_span_id 对齐。"""
    tracer = Tracer()
    tracer.start(trace_id=42)

    root = tracer.span("root", "db").__enter__()
    child = tracer.span("child", "llm", parent_id=root.span_id).__enter__()
    child.__exit__(None, None, None)
    root.__exit__(None, None, None)

    _flush_tracer(tracer, pipeline_env.session)

    spans = list(
        pipeline_env.session.scalars(
            select(TraceSpan).where(TraceSpan.trace_id == 42).order_by(TraceSpan.id)
        )
    )
    assert len(spans) == 2
    root_row = next(s for s in spans if s.name == "root")
    child_row = next(s for s in spans if s.name == "child")
    assert root_row.parent_span_id is None
    assert child_row.parent_span_id == root_row.id


def test_tracer_flush_is_idempotent(pipeline_env):
    """flush 后再 flush 不重复落库（span 只 insert 一次）。"""
    tracer = Tracer()
    tracer.start(trace_id=7)
    with tracer.span("gen_ai.chat", "llm"):
        pass
    _flush_tracer(tracer, pipeline_env.session)
    tracer.flush(pipeline_env.session)  # 二次 flush 应为空操作

    spans = list(
        pipeline_env.session.scalars(select(TraceSpan).where(TraceSpan.trace_id == 7))
    )
    assert len(spans) == 1


def test_tracer_flush_swallows_db_error(pipeline_env):
    """flush 时 DB 异常不抛——观测写库失败绝不打断问答。"""
    tracer = Tracer()
    tracer.start(trace_id=9)
    with tracer.span("gen_ai.chat", "llm"):
        pass

    class _BoomSession:
        def add_all(self, *a, **k):
            raise RuntimeError("db down")

        def add(self, *a, **k):
            raise RuntimeError("db down")

    tracer.flush(_BoomSession())  # 不应抛出


def test_span_context_as_decorator_style(pipeline_env):
    """SpanContext 的 token/input/output/cost setter 全部生效且不强制调用。"""
    tracer = Tracer()
    tracer.start(trace_id=5)
    with tracer.span("gen_ai.chat", "llm") as s:
        s.set_tokens(in_tokens=100, out_tokens=200)
        s.set_input_summary("q")
        s.set_output_summary("a")
        s.set_cost(Decimal("0.01"))
    _flush_tracer(tracer, pipeline_env.session)

    span = pipeline_env.session.scalar(select(TraceSpan).where(TraceSpan.trace_id == 5))
    assert span.gen_ai_usage_tokens_in == 100
    assert span.gen_ai_usage_tokens_out == 200
    assert span.input_summary == "q"
    assert span.output_summary == "a"
    assert span.cost == Decimal("0.01")
