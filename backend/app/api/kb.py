"""知识库管理 API（Task 3，挂载于 /api/v1/admin/kbs）。

JWT 鉴权属 Task 14——当前由部署层 IP 白名单兜底（技术决策记录 §2.1）。
「仅空库可删」（设计文档 §7）：库内仍有 document 时 409。
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models import Document, KnowledgeBase
from app.schemas import KBCreate, KBOut, KBPatch

router = APIRouter(prefix="/kbs", tags=["知识库"])


def _commit_or_409(db: Session) -> None:
    """check-then-write 窗口的并发同名由唯一约束兜底（IntegrityError → 409 而非 500）。"""
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail="知识库名已存在") from None


def _get_or_404(db: Session, kb_id: int) -> KnowledgeBase:
    kb = db.get(KnowledgeBase, kb_id)
    if kb is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="知识库不存在")
    return kb


def _name_taken(db: Session, name: str, *, exclude_id: int | None = None) -> bool:
    stmt = select(func.count()).select_from(KnowledgeBase).where(KnowledgeBase.name == name)
    if exclude_id is not None:
        stmt = stmt.where(KnowledgeBase.id != exclude_id)
    return bool(db.scalar(stmt))


@router.post("", status_code=status.HTTP_201_CREATED, response_model=KBOut)
def create_kb(payload: KBCreate, db: Session = Depends(get_db)) -> KnowledgeBase:
    """创建知识库（重名 409；name 唯一约束兜底）。"""
    if _name_taken(db, payload.name):
        raise HTTPException(status.HTTP_409_CONFLICT, detail="知识库名已存在")
    kb = KnowledgeBase(name=payload.name, description=payload.description)
    db.add(kb)
    _commit_or_409(db)
    db.refresh(kb)  # 回填库端默认值（created_at）
    return kb


@router.get("", response_model=list[KBOut])
def list_kbs(db: Session = Depends(get_db)) -> list[KnowledgeBase]:
    """知识库列表（按 id 升序）。"""
    return list(db.scalars(select(KnowledgeBase).order_by(KnowledgeBase.id)).all())


@router.patch("/{kb_id}", response_model=KBOut)
def patch_kb(kb_id: int, payload: KBPatch, db: Session = Depends(get_db)) -> KnowledgeBase:
    """局部更新（name/description/status；改名撞唯一约束 409）。"""
    kb = _get_or_404(db, kb_id)
    if payload.name is not None and payload.name != kb.name and _name_taken(db, payload.name):
        raise HTTPException(status.HTTP_409_CONFLICT, detail="知识库名已存在")
    # exclude_none：显式 null = 未提供（KBPatch 契约「未给的（None）不改」），否则落库 NOT NULL 必炸
    for field, value in payload.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(kb, field, value)
    _commit_or_409(db)
    db.refresh(kb)
    return kb


@router.delete("/{kb_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_kb(kb_id: int, db: Session = Depends(get_db)) -> None:
    """删除知识库（仅空库可删；非空 409）。"""
    kb = _get_or_404(db, kb_id)
    doc_count = db.scalar(select(func.count()).select_from(Document).where(Document.kb_id == kb_id))
    if doc_count:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="库内仍有文档，不可删除")
    db.delete(kb)
    db.commit()
