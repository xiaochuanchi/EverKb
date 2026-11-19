"""平台概况 API（dashboard 运营驾驶舱，挂载于 /api/v1/admin/dashboard）。

一次性聚合概况页所需全部统计（纯 MySQL 聚合，无向量依赖，轻量快速）：
- 计数：知识库 / 文档 / chunk / 应用 / 问答 / 累计花费 / 失败文档；
- 趋势：近 14 天每日问答数（缺失日期补 0）；
- 分布：文档状态分布、应用检索模式分布（dense/hybrid）；
- 最近问答：Top 5（供首页列表 + 跳 Trace）。

对账漂移数不在此接口（依赖 VectorClient 全量扫描，较重），由前端复用
GET /reconciliation 单独取，非关键路径可延迟加载。
"""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.envelope import EnvelopeRoute
from app.core.db import get_db
from app.models import App, Chunk, Document, DocumentStatus, KnowledgeBase, QaRecord
from app.schemas import (
    DashboardDocStatusItem,
    DashboardOut,
    DashboardRecentQa,
    DashboardRetrievalModeItem,
    DashboardTrendPoint,
)

router = APIRouter(prefix="/dashboard", tags=["平台概况"], route_class=EnvelopeRoute)

_TREND_DAYS = 14
_RECENT_QA_N = 5


@router.get("", response_model=DashboardOut)
def dashboard(db: Session = Depends(get_db)) -> dict:
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

    # ── 近 14 天问答趋势（缺失日期补 0）──────────────────────────
    since = datetime.now() - timedelta(days=_TREND_DAYS - 1)
    # 按日期分组计数（跨 MySQL/SQLite：func.date 均可用）
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

    return {
        "kb_count": kb_count,
        "doc_count": doc_count,
        "chunk_count": chunk_count,
        "app_count": app_count,
        "qa_count": qa_count,
        "total_cost": float(total_cost),
        "failed_doc_count": failed_doc_count,
        "qa_trend": qa_trend,
        "doc_status": doc_status,
        "retrieval_modes": retrieval_modes,
        "recent_qa": recent_qa,
    }
