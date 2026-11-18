"""Trace 查看 API（Task 22，挂载于 /api/v1/admin/traces）。

管理后台「Trace 查看器」：记录点开 → Span 树（parent_span_id 成树，按 start_time 排序）；
跨 Trace 聚合：最慢调用 Top N + 各 span_type 的 P95 耗时 / 平均 token / 平均花费。
"""
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.envelope import EnvelopeRoute
from app.core.db import get_db
from app.models import QaRecord, TraceSpan
from app.schemas import (
    SpanAggregateItem,
    TraceAggregateOut,
    TraceSpanNode,
    TraceSpanOut,
    TraceTreeOut,
)

router = APIRouter(prefix="/traces", tags=["Trace"], route_class=EnvelopeRoute)

_SLOWEST_TOP_N = 10


def _span_to_node(span: TraceSpan, children: list[TraceSpanNode]) -> TraceSpanNode:
    return TraceSpanNode(
        id=span.id,
        name=span.name,
        span_type=span.span_type,
        parent_span_id=span.parent_span_id,
        input_summary=span.input_summary,
        output_summary=span.output_summary,
        start_time=span.start_time,
        end_time=span.end_time,
        latency_ms=span.latency_ms,
        gen_ai_usage_tokens_in=span.gen_ai_usage_tokens_in,
        gen_ai_usage_tokens_out=span.gen_ai_usage_tokens_out,
        cost=float(span.cost) if span.cost is not None else None,
        extra=span.extra,
        children=children,
    )


def _build_tree(spans: list[TraceSpan]) -> list[TraceSpanNode]:
    """按 parent_span_id 成树；每层按 start_time 排序。"""
    by_parent: dict[int | None, list[TraceSpan]] = {}
    for s in spans:
        by_parent.setdefault(s.parent_span_id, []).append(s)
    for group in by_parent.values():
        group.sort(key=lambda s: s.start_time)

    def build(parent_id: int | None) -> list[TraceSpanNode]:
        nodes = []
        for s in by_parent.get(parent_id, []):
            nodes.append(_span_to_node(s, build(s.id)))
        return nodes

    return build(None)


def _p95(values: list[int]) -> int | None:
    """P95 分位（最近秩法）：空返回 None。"""
    if not values:
        return None
    values = sorted(values)
    idx = int((len(values) - 1) * 0.95)
    return values[idx]


@router.get("/aggregate", response_model=TraceAggregateOut)
def aggregate(
    db: Session = Depends(get_db),
) -> dict:
    """跨 Trace 聚合：最慢调用 Top N + 各 span_type 的 P95/平均 token/平均花费。"""
    all_spans = db.scalars(select(TraceSpan)).all()

    # 最慢 Top N
    slowest = sorted(all_spans, key=lambda s: s.latency_ms, reverse=True)[:_SLOWEST_TOP_N]

    # 按 span_type 分组聚合
    by_type: dict[str, list[TraceSpan]] = {}
    for s in all_spans:
        by_type.setdefault(s.span_type, []).append(s)

    type_items = []
    for span_type, spans in sorted(by_type.items()):
        latencies = [s.latency_ms for s in spans]
        tokens_in = [s.gen_ai_usage_tokens_in for s in spans if s.gen_ai_usage_tokens_in is not None]
        tokens_out = [s.gen_ai_usage_tokens_out for s in spans if s.gen_ai_usage_tokens_out is not None]
        costs = [float(s.cost) for s in spans if s.cost is not None]
        type_items.append(SpanAggregateItem(
            span_type=span_type,
            count=len(spans),
            p95_latency_ms=_p95(latencies),
            avg_tokens_in=round(sum(tokens_in) / len(tokens_in), 2) if tokens_in else None,
            avg_tokens_out=round(sum(tokens_out) / len(tokens_out), 2) if tokens_out else None,
            avg_cost=round(sum(costs) / len(costs), 6) if costs else None,
        ))

    return {
        "slowest": [TraceSpanOut.model_validate(s) for s in slowest],
        "by_type": type_items,
    }


@router.get("/{record_id}", response_model=TraceTreeOut)
def trace_tree(record_id: int, db: Session = Depends(get_db)) -> dict:
    """单条问答的 span 树（parent_span_id 成树，按 start_time 排序）。"""
    rec = db.get(QaRecord, record_id)
    if rec is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="问答记录不存在")
    spans = db.scalars(
        select(TraceSpan).where(TraceSpan.trace_id == record_id)
    ).all()
    return {"record_id": record_id, "spans": _build_tree(spans)}
