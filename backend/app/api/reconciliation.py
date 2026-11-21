"""对账 API（挂载于 /api/v1/admin）。

扫描 status==6（已完成）文档的漂移：
- unvectorized：MySQL 存在 vectorized=False 的 chunk 行（向量未入库却显示完成）
- count_mismatch：MySQL chunk 行数 != Milvus 侧 count_by_doc（向量残留或多删）

未完成（status!=6）文档天然 chunk 数与向量未对齐，不参与对账。
多租户（M1/M5）：require_enterprise，仅扫描当前企业文档。
"""
from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.authz import require_enterprise
from app.api.envelope import EnvelopeRoute
from app.core.db import get_db
from app.models import AdminUser, Chunk, Document, DocumentStatus
from app.schemas import ReconciliationItemOut
from app.services.vector import VectorClient

router = APIRouter(tags=["对账"], route_class=EnvelopeRoute)


def _vector(request: Request) -> VectorClient:
    return request.app.state.vector


@router.get("/reconciliation", response_model=list[ReconciliationItemOut])
def reconciliation(
    user: AdminUser = Depends(require_enterprise),
    db: Session = Depends(get_db),
    vector: VectorClient = Depends(_vector),
) -> list[dict]:
    """返回已完成文档的漂移清单（仅当前企业）：每元素 {doc_id, issue}。"""
    completed_docs = db.scalars(
        select(Document).where(
            Document.enterprise_id == user.enterprise_id,
            Document.status == DocumentStatus.COMPLETED,
        )
    ).all()
    issues: list[dict] = []
    for doc in completed_docs:
        doc_issues = _scan_doc(db, vector, doc)
        for issue in doc_issues:
            issues.append({"doc_id": doc.id, "issue": issue})
    return issues


def _scan_doc(db: Session, vector: VectorClient, doc: Document) -> list[str]:
    """单文档漂移扫描：先 unvectorized，再 count_mismatch（两者可同时命中）。"""
    found: list[str] = []
    unvectorized = db.scalar(
        select(func.count())
        .select_from(Chunk)
        .where(Chunk.document_id == doc.id, Chunk.vectorized.is_(False))
    )
    if unvectorized:
        found.append("unvectorized")
    mysql_count = db.scalar(
        select(func.count()).select_from(Chunk).where(Chunk.document_id == doc.id)
    )
    vector_count = vector.count_by_doc(doc.id)
    if mysql_count != vector_count:
        found.append("count_mismatch")
    return found
