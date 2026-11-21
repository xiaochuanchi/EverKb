"""通知中心 API（挂载于 /api/v1/admin/notifications）。

管理后台右上角通知中心：分页列表（按 created_at 倒序，含未读数）+
标记单条已读 + 全部已读。通知来源为文档处理管线完成/失败事件。
多租户（M1/M5）：require_enterprise + scoped/ensure_owned 按 enterprise_id 隔离。
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.authz import ensure_owned, require_enterprise
from app.api.envelope import EnvelopeRoute
from app.core.db import get_db
from app.models import AdminUser, Notification
from app.schemas import NotificationOut, NotificationPageOut

router = APIRouter(prefix="/notifications", tags=["通知中心"], route_class=EnvelopeRoute)


def _get_owned_or_404(db: Session, notification_id: int, ent_id: int) -> Notification:
    n = db.get(Notification, notification_id)
    ensure_owned(db, n, ent_id)
    return n


@router.get("", response_model=NotificationPageOut)
def list_notifications(
    unread_only: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=200),
    user: AdminUser = Depends(require_enterprise),
    db: Session = Depends(get_db),
) -> dict:
    """通知分页（仅当前企业，按 id 倒序）。unread_only=true 时仅未读。"""
    base = [Notification.enterprise_id == user.enterprise_id]
    conds = base + [Notification.is_read.is_(False)] if unread_only else base

    total = db.scalar(select(func.count()).select_from(Notification).where(*conds))
    unread = db.scalar(
        select(func.count())
        .select_from(Notification)
        .where(Notification.enterprise_id == user.enterprise_id, Notification.is_read.is_(False))
    )
    items = db.scalars(
        select(Notification)
        .where(*conds)
        .order_by(Notification.id.desc())
        .offset((page - 1) * size)
        .limit(size)
    ).all()
    return {
        "total": total,
        "unread": unread,
        "page": page,
        "size": size,
        "items": list(items),
    }


@router.get("/unread-count")
def unread_count(
    user: AdminUser = Depends(require_enterprise),
    db: Session = Depends(get_db),
) -> dict:
    """未读通知数（仅当前企业，供铃铛红点角标）。"""
    count = db.scalar(
        select(func.count())
        .select_from(Notification)
        .where(Notification.enterprise_id == user.enterprise_id, Notification.is_read.is_(False))
    )
    return {"unread": count}


@router.post("/{notification_id}/read", response_model=NotificationOut)
def mark_read(
    notification_id: int,
    user: AdminUser = Depends(require_enterprise),
    db: Session = Depends(get_db),
) -> Notification:
    """标记单条已读。"""
    n = _get_owned_or_404(db, notification_id, user.enterprise_id)
    n.is_read = True
    db.commit()
    db.refresh(n)
    return n


@router.post("/read-all")
def mark_all_read(
    user: AdminUser = Depends(require_enterprise),
    db: Session = Depends(get_db),
) -> dict:
    """全部标记已读（仅当前企业）。"""
    db.query(Notification).filter(
        Notification.enterprise_id == user.enterprise_id, Notification.is_read.is_(False)
    ).update({Notification.is_read: True}, synchronize_session=False)
    db.commit()
    return {"ok": True}
