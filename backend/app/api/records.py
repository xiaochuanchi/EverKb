"""问答记录 API（Task 22，挂载于 /api/v1/admin/records）。

管理后台「问答记录」页：分页列表（可按 app_id / feedback 筛选）+ 单条详情。
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.envelope import EnvelopeRoute
from app.core.db import get_db
from app.models import QaRecord
from app.schemas import QaRecordOut, QaRecordPageOut

router = APIRouter(prefix="/records", tags=["问答记录"], route_class=EnvelopeRoute)


def _get_record_or_404(db: Session, record_id: int) -> QaRecord:
    rec = db.get(QaRecord, record_id)
    if rec is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="问答记录不存在")
    return rec


@router.get("", response_model=QaRecordPageOut)
def list_records(
    app_id: int | None = Query(default=None),
    feedback: int | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict:
    """问答记录分页（按 created_at 倒序，最新在前）。可按 app_id / feedback 筛选。"""
    conds = []
    if app_id is not None:
        conds.append(QaRecord.app_id == app_id)
    if feedback is not None:
        conds.append(QaRecord.feedback == feedback)

    total = db.scalar(select(func.count()).select_from(QaRecord).where(*conds))
    items = db.scalars(
        select(QaRecord)
        .where(*conds)
        .order_by(QaRecord.id.desc())
        .offset((page - 1) * size)
        .limit(size)
    ).all()
    return {"total": total, "page": page, "size": size, "items": list(items)}


@router.get("/{record_id}", response_model=QaRecordOut)
def get_record(record_id: int, db: Session = Depends(get_db)) -> QaRecord:
    """单条问答记录详情（含 question/answer/citations/feedback）。"""
    return _get_record_or_404(db, record_id)
