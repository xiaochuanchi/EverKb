"""平台概况 API（dashboard 运营驾驶舱，挂载于 /api/v1/admin/dashboard）。

一次性聚合概况页所需全部统计：
- 计数：知识库 / 文档 / chunk / 应用 / 问答 / 累计花费 / 失败文档 / 漂移文档；
- 趋势：近 14 天每日问答数（缺失日期补 0）；
- 环比：近 7 天 vs 前 7 天（各实体新增量、花费金额）的涨跌；
- 分布：文档状态分布、应用检索模式分布（dense/hybrid）；
- 最近问答：Top 5（供首页列表 + 跳 Trace）。

漂移文档数依赖 VectorClient（复用对账扫描逻辑），仅在已完成文档上统计，
未完成文档天然 chunk 数与向量未对齐，不参与对账（与 /reconciliation 同口径）。
"""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.envelope import EnvelopeRoute
from app.api.reconciliation import _scan_doc
from app.core.db import get_db
from app.models import App, Chunk, Document, DocumentStatus, KnowledgeBase, QaRecord
from app.schemas import (
    DashboardDocStatusItem,
    DashboardKpiTrend,
    DashboardOut,
    DashboardRecentQa,
    DashboardRetrievalModeItem,
    DashboardTrendPoint,
)
from app.services.vector import VectorClient

router = APIRouter(prefix="/dashboard", tags=["平台概况"], route_class=EnvelopeRoute)

_TREND_DAYS = 14
_RECENT_QA_N = 5
_MOM_WINDOW_DAYS = 7  # 环比窗口：近 7 天 vs 前 7 天


def _vector(request: Request) -> VectorClient:
    return request.app.state.vector


def _pct_change(current: float, previous: float) -> float | None:
    """环比涨跌百分比；上周期为 0 时记 None（无基数不可比，前端显示「—」）。"""
    if previous == 0:
        return None
    return round((current - previous) / previous, 4)


@router.get("", response_model=DashboardOut)
def dashboard(
    db: Session = Depends(get_db),
    vector: VectorClient = Depends(_vector),
) -> dict:
    """返回概况页全部统计。"""
    kb_count = db.scalar(select(func.count()).select_from(KnowledgeBase)) or 0
    doc_count = db.scalar(select(func.count()).select_from(Document)) or 0
    chunk_count = db.scalar(select(func.count()).select_from(Chunk)) or 0
    app_count = db.scalar(select(func.count()).select_from(App)) or 0
    qa_count = db.scalar(select(func.count()).select_from(QaRecord)) or 0
    total_cost = db.scalar(select(func.coalesce(func.sum(QaRecord.total_cost), 0))) or 0
    failed_doc_count = (
        db.scalar(
            select(func.count())
            .select_from(Document)
            .where(Document.status == DocumentStatus.FAILED)
        )
        or 0
    )

    # ── 漂移文档数（复用对账扫描逻辑，仅已完成文档）─────────────────
    completed_docs = db.scalars(
        select(Document).where(Document.status == DocumentStatus.COMPLETED)
    ).all()
    drift_doc_count = sum(1 for d in completed_docs if _scan_doc(db, vector, d))

    # ── 近 14 天问答趋势（缺失日期补 0）──────────────────────────
    since = datetime.now() - timedelta(days=_TREND_DAYS - 1)
    rows = db.execute(
        select(func.date(QaRecord.created_at), func.count())
        .where(QaRecord.created_at >= since)
        .group_by(func.date(QaRecord.created_at))
        .order_by(func.date(QaRecord.created_at))
    ).all()
    by_date = {str(d): c for d, c in rows}
    qa_trend: list[DashboardTrendPoint] = []
    today = datetime.now().date()
    for i in range(_TREND_DAYS - 1, -1, -1):
        day = today - timedelta(days=i)
        key = day.isoformat()
        qa_trend.append(DashboardTrendPoint(date=key, count=by_date.get(key, 0)))

    # ── 文档状态分布（按 status 分组，全状态枚举补 0）─────────────
    status_rows = db.execute(
        select(Document.status, func.count())
        .group_by(Document.status)
        .order_by(Document.status)
    ).all()
    status_map = {s: c for s, c in status_rows}
    doc_status = [
        DashboardDocStatusItem(status=s, count=status_map.get(s, 0))
        for s in range(1, 8)  # DocumentStatus 1..7
    ]

    # ── 检索模式分布（dense/hybrid）──────────────────────────────
    mode_rows = db.execute(
        select(App.retrieval_mode, func.count()).group_by(App.retrieval_mode)
    ).all()
    retrieval_modes = [
        DashboardRetrievalModeItem(mode=m, count=c) for m, c in mode_rows
    ]

    # ── 最近问答 Top 5 ────────────────────────────────────────────
    recent_rows = db.scalars(
        select(QaRecord).order_by(QaRecord.created_at.desc()).limit(_RECENT_QA_N)
    ).all()
    recent_qa = [
        DashboardRecentQa(
            id=r.id,
            app_id=r.app_id,
            question=r.question,
            grounded=r.grounded,
            latency_ms=r.latency_ms,
            created_at=r.created_at,
        )
        for r in recent_rows
    ]

    # ── 环比（近 7 天 vs 前 7 天）────────────────────────────────
    now = datetime.now()
    cur_start = now - timedelta(days=_MOM_WINDOW_DAYS)
    prev_start = now - timedelta(days=_MOM_WINDOW_DAYS * 2)

    def _count_range(model) -> tuple[int, int]:
        """统计 [prev_start, cur_start) 与 [cur_start, now) 两段的新增行数。"""
        prev = db.scalar(
            select(func.count())
            .select_from(model)
            .where(model.created_at >= prev_start, model.created_at < cur_start)
        ) or 0
        cur = db.scalar(
            select(func.count())
            .select_from(model)
            .where(model.created_at >= cur_start)
        ) or 0
        return cur, prev

    def _build_kpi(cur: int | float, prev: int | float) -> DashboardKpiTrend:
        return DashboardKpiTrend(current=cur, previous=prev, pct_change=_pct_change(cur, prev))

    # 花费环比：两段金额合计（total_cost）
    prev_cost = db.scalar(
        select(func.coalesce(func.sum(QaRecord.total_cost), 0)).where(
            QaRecord.created_at >= prev_start, QaRecord.created_at < cur_start
        )
    ) or 0
    cur_cost = db.scalar(
        select(func.coalesce(func.sum(QaRecord.total_cost), 0)).where(
            QaRecord.created_at >= cur_start
        )
    ) or 0

    kpi_trend = {
        "kb": _build_kpi(*_count_range(KnowledgeBase)),
        "doc": _build_kpi(*_count_range(Document)),
        "chunk": _build_kpi(*_count_range(Chunk)),
        "app": _build_kpi(*_count_range(App)),
        "qa": _build_kpi(*_count_range(QaRecord)),
        "cost": _build_kpi(float(cur_cost), float(prev_cost)),
    }

    return {
        "kb_count": kb_count,
        "doc_count": doc_count,
        "chunk_count": chunk_count,
        "app_count": app_count,
        "qa_count": qa_count,
        "total_cost": float(total_cost),
        "failed_doc_count": failed_doc_count,
        "drift_doc_count": drift_doc_count,
        "qa_trend": qa_trend,
        "doc_status": doc_status,
        "retrieval_modes": retrieval_modes,
        "recent_qa": recent_qa,
        "kpi_trend": kpi_trend,
    }
