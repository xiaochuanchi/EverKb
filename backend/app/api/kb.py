"""知识库管理 API（挂载于 /api/v1/admin/kbs）。

多租户（M1/M5）：所有端点走 require_enterprise（ENT_ADMIN/MEMBER + 企业绑定），
列表/单对象一律 scoped/ensure_owned 按 enterprise_id 隔离，杜绝跨企业越权。
「仅空库可删」（设计文档 §7）：库内仍有 document 时 409。
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.authz import ensure_owned, require_enterprise, scoped
from app.api.envelope import EnvelopeRoute
from app.core.db import get_db
from app.models import AdminUser, Document, KnowledgeBase
from app.schemas import KBCreate, KBOut, KBPatch

router = APIRouter(prefix="/kbs", tags=["知识库"], route_class=EnvelopeRoute)


def _commit_or_409(db: Session) -> None:
    """check-then-write 窗口的并发同名由唯一约束兜底（IntegrityError → 409 而非 500）。"""
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail="知识库名已存在") from None


def _get_owned_or_404(db: Session, kb_id: int, ent_id: int) -> KnowledgeBase:
    """取知识库并校验归属（跨企业访问 → 404，不泄露存在性）。"""
    kb = db.get(KnowledgeBase, kb_id)
    ensure_owned(db, kb, ent_id)
    return kb


def _name_taken(db: Session, ent_id: int, name: str, *, exclude_id: int | None = None) -> bool:
    """同名检测按企业隔离（企业内重名 409，跨企业同名允许）。"""
    stmt = (
        select(func.count())
        .select_from(KnowledgeBase)
        .where(KnowledgeBase.enterprise_id == ent_id, KnowledgeBase.name == name)
    )
    if exclude_id is not None:
        stmt = stmt.where(KnowledgeBase.id != exclude_id)
    return bool(db.scalar(stmt))


@router.post("", status_code=status.HTTP_201_CREATED, response_model=KBOut)
def create_kb(
    payload: KBCreate,
    user: AdminUser = Depends(require_enterprise),
    db: Session = Depends(get_db),
) -> KnowledgeBase:
    """创建知识库（企业内重名 409；挂当前企业 enterprise_id）。"""
    if _name_taken(db, user.enterprise_id, payload.name):
        raise HTTPException(status.HTTP_409_CONFLICT, detail="知识库名已存在")
    kb = KnowledgeBase(
        name=payload.name, description=payload.description, enterprise_id=user.enterprise_id
    )
    db.add(kb)
    _commit_or_409(db)
    db.refresh(kb)  # 回填库端默认值（created_at）
    return kb


@router.get("", response_model=list[KBOut])
def list_kbs(
    user: AdminUser = Depends(require_enterprise),
    db: Session = Depends(get_db),
) -> list[KnowledgeBase]:
    """知识库列表（仅当前企业，按 id 升序）。"""
    return list(db.scalars(scoped(db, KnowledgeBase, user.enterprise_id).order_by(KnowledgeBase.id)).all())


@router.patch("/{kb_id}", response_model=KBOut)
def patch_kb(
    kb_id: int,
    payload: KBPatch,
    user: AdminUser = Depends(require_enterprise),
    db: Session = Depends(get_db),
) -> KnowledgeBase:
    """局部更新（name/description/status；企业内改名撞唯一约束 409）。"""
    kb = _get_owned_or_404(db, kb_id, user.enterprise_id)
    if payload.name is not None and payload.name != kb.name and _name_taken(
        db, user.enterprise_id, payload.name, exclude_id=kb.id
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, detail="知识库名已存在")
    # exclude_none：显式 null = 未提供（KBPatch 契约「未给的（None）不改」），否则落库 NOT NULL 必炸
    for field, value in payload.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(kb, field, value)
    _commit_or_409(db)
    db.refresh(kb)
    return kb


@router.delete("/{kb_id}")
def delete_kb(
    kb_id: int,
    user: AdminUser = Depends(require_enterprise),
    db: Session = Depends(get_db),
) -> None:
    """删除知识库（仅空库可删；非空 409）。"""
    kb = _get_owned_or_404(db, kb_id, user.enterprise_id)
    doc_count = db.scalar(select(func.count()).select_from(Document).where(Document.kb_id == kb_id))
    if doc_count:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="库内仍有文档，不可删除")
    db.delete(kb)
    db.commit()
