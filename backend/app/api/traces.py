"""Trace 查看 API（挂载于 /api/v1/admin/traces）。

管理后台「Trace 查看器」：记录点开 → Span 树（parent_span_id 成树，按 start_time 排序）；
跨 Trace 聚合：最慢调用 Top N + 各 span_type 的 P95 耗时 / 平均 token / 平均花费。
多租户（M1/M5）：require_enterprise + enterprise_id 过滤（span 自带 enterprise_id）。
"""
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.authz import ensure_owned, require_enterprise
from app.api.envelope import EnvelopeRoute
from app.core.db import get_db
from app.models import AdminUser, Document, QaRecord, TraceSpan
from app.schemas import (
    DocumentOut,
    PipelineTraceItem,
    PipelineTracePageOut,
    SpanAggregateItem,
    TraceAggregateOut,
    TraceSpanNode,
    TraceSpanOut,
    TraceTreeOut,
)

router = APIRouter(prefix="/traces", tags=["Trace"], route_class=EnvelopeRoute)

_SLOWEST_TOP_N = 10

# 入库链路 trace_id 命名空间：-(doc_id)，与问答 qa_record.id（正整数）符号隔离
# （与 pipeline._PIPELINE_TRACE_ID_OFFSET 对齐，此处常量仅作语义说明，不参与计算）
_PIPELINE_TRACE_PREFIX = "-"


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
    user: AdminUser = Depends(require_enterprise),
    db: Session = Depends(get_db),
) -> dict:
    """跨 Trace 聚合：最慢调用 Top N + 各 span_type 的 P95/平均 token/平均花费（仅当前企业）。"""
    all_spans = db.scalars(
        select(TraceSpan).where(TraceSpan.enterprise_id == user.enterprise_id)
    ).all()

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


@router.get("/pipeline", response_model=PipelineTracePageOut)
def pipeline_traces(
    user: AdminUser = Depends(require_enterprise),
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
) -> dict:
    """入库链路 Trace 列表（仅当前企业）：管线 span 的 trace_id 为负数（-(doc_id)）。

    按 trace_id 分组统计 span 数 / 总耗时 / 最近时间，左连 document 取文档名，
    便于查看器从「入库链路」入口点进 span 树。
    """
    rows = db.execute(
        select(
            TraceSpan.trace_id,
            func.count(TraceSpan.id),
            func.sum(TraceSpan.latency_ms),
            func.max(TraceSpan.start_time),
        )
        .where(TraceSpan.trace_id < 0, TraceSpan.enterprise_id == user.enterprise_id)
        .group_by(TraceSpan.trace_id)
        .order_by(TraceSpan.trace_id)
    ).all()

    total = len(rows)
    page_rows = rows[(page - 1) * size : page * size]

    # 批量取关联文档（doc_id = -trace_id），并限定当前企业
    doc_ids = [(-r[0]) for r in page_rows]
    docs: dict[int, Document] = {}
    if doc_ids:
        for d in db.scalars(
            select(Document).where(
                Document.id.in_(doc_ids), Document.enterprise_id == user.enterprise_id
            )
        ).all():
            docs[d.id] = d

    items: list[PipelineTraceItem] = []
    for trace_id, cnt, latency_sum, last_time in page_rows:
        doc = docs.get(-trace_id)
        items.append(
            PipelineTraceItem(
                trace_id=trace_id,
                doc_id=-trace_id,
                doc_name=doc.name if doc else None,
                kb_id=doc.kb_id if doc else None,
                doc_status=doc.status if doc else None,
                span_count=cnt,
                total_latency_ms=int(latency_sum or 0),
                last_start_time=last_time,
            )
        )

    return {"total": total, "page": page, "size": size, "items": items}


@router.get("/{trace_id}", response_model=TraceTreeOut)
def trace_tree(
    trace_id: int,
    user: AdminUser = Depends(require_enterprise),
    db: Session = Depends(get_db),
) -> dict:
    """单条问答 / 入库链路的 span 树（parent_span_id 成树，按 start_time 排序）。

    trace_id 二义：正数 = qa_record.id（问答）；负数 = -(doc_id)（管线入库）。
    """
    spans = db.scalars(
        select(TraceSpan).where(
            TraceSpan.trace_id == trace_id, TraceSpan.enterprise_id == user.enterprise_id
        )
    ).all()

    if trace_id >= 0:
        # 问答链路：校验 qa_record 存在且属于当前企业
        rec = db.get(QaRecord, trace_id)
        ensure_owned(db, rec, user.enterprise_id)
        return {
            "trace_id": trace_id,
            "source": "qa",
            "spans": _build_tree(spans),
            "doc": None,
        }

    # 入库链路：负数 trace_id，关联文档（校验归属）
    doc = db.get(Document, -trace_id)
    ensure_owned(db, doc, user.enterprise_id)
    if not spans:
        # 无 span 且无文档 → 视为不存在（与问答 404 语义一致）
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="入库 Trace 不存在")
    return {
        "trace_id": trace_id,
        "source": "pipeline",
        "spans": _build_tree(spans),
        "doc": DocumentOut.model_validate(doc) if doc else None,
    }
