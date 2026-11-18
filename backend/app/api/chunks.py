"""chunk 浏览 API（Task 13，挂载于 /api/v1/admin/documents）。

按 chunk_index 升序分页返回切块，供管理后台「chunk 浏览页」逐块查看。
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.envelope import EnvelopeRoute
from app.core.db import get_db
from app.models import Chunk, Document
from app.schemas import ChunkPageOut

router = APIRouter(prefix="/documents", tags=["文档"], route_class=EnvelopeRoute)


def _get_doc_or_404(db: Session, doc_id: int) -> Document:
    doc = db.get(Document, doc_id)
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="文档不存在")
    return doc


@router.get("/{doc_id}/chunks", response_model=ChunkPageOut)
def list_chunks(
    doc_id: int,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict:
    """文档切块分页列表（按 chunk_index 升序）。"""
    _get_doc_or_404(db, doc_id)
    total = db.scalar(
        select(func.count()).select_from(Chunk).where(Chunk.document_id == doc_id)
    )
    items = db.scalars(
        select(Chunk)
        .where(Chunk.document_id == doc_id)
        .order_by(Chunk.chunk_index, Chunk.id)
        .offset((page - 1) * size)
        .limit(size)
    ).all()
    return {"total": total, "page": page, "size": size, "items": list(items)}
