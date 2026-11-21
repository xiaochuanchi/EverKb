"""chunk 浏览 API（挂载于 /api/v1/admin/documents）。

按 chunk_index 升序分页返回切块，供管理后台「chunk 浏览页」逐块查看。
多租户（M1/M5）：chunk 无 enterprise_id，经 doc 归属校验（require_enterprise + ensure_owned）。
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.authz import ensure_owned, require_enterprise
from app.api.envelope import EnvelopeRoute
from app.core.db import get_db
from app.models import AdminUser, Chunk, Document
from app.schemas import ChunkPageOut

router = APIRouter(prefix="/documents", tags=["文档"], route_class=EnvelopeRoute)


def _get_owned_doc_or_404(db: Session, doc_id: int, ent_id: int) -> Document:
    doc = db.get(Document, doc_id)
    ensure_owned(db, doc, ent_id)
    return doc


@router.get("/{doc_id}/chunks", response_model=ChunkPageOut)
def list_chunks(
    doc_id: int,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=200),
    user: AdminUser = Depends(require_enterprise),
    db: Session = Depends(get_db),
) -> dict:
    """文档切块分页列表（按 chunk_index 升序）。"""
    _get_owned_doc_or_404(db, doc_id, user.enterprise_id)
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
