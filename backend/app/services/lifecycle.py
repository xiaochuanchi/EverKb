"""企业生命周期状态机（M3，设计出处《商业化多租户设计方案 2026-11-20》§7）。

状态机（EnterpriseStatus）：
    1 TRIAL 试用中 ──trial_ends_at 到期──▶ 3 FROZEN 只读冻结
    2 ACTIVE 正式  ──service_ends_at 到期─▶ 3 FROZEN
    3 FROZEN ──data_purge_at 到期──▶ 4 PURGED（清理业务数据，企业行保留）

关键纪律（对齐方案 §7）：
- 只读冻结：冻结企业问答/管理 403，不触 embedding/LLM（零成本），但登录与
  浏览数据仍允许（转化钩子，数据在 = 充值即恢复）。
- 清理顺序红线（复用删除红线）：Milvus 向量 → chunk 行 → doc 行 → 存储对象；
  企业行与钱包流水保留（审计）。
- 所有跃迁幂等：重复执行不重复通知、不重复清理，可安全重跑。
"""
import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    App,
    Chunk,
    Document,
    Enterprise,
    EnterpriseStatus,
    KnowledgeBase,
    Notification,
    NotificationType,
    QaRecord,
)
from app.services.pipeline import content_key_for

logger = logging.getLogger("everkb.lifecycle")

# 冻结起算到数据清理的天数（方案 §7：只读冻结，数据保留 60 天后清理）
_PURGE_AFTER_DAYS = 60
# 到期前提前通知天数（方案 §7：到期前 7 天提醒企业管理员）
_NOTIFY_BEFORE_DAYS = 7


def _now() -> datetime:
    """可被测试打桩的当前时刻（naive，与 DB TIMESTAMP 对齐）。"""
    return datetime.now()


def transition_expired(session: Session, now: datetime | None = None) -> int:
    """试用/服务到期 → FROZEN；返回本轮回转冻结的企业数。

    幂等：只处理仍处于 TRIAL/ACTIVE 且已过期的企业；已冻结/已清理不动。
    """
    now = now or _now()
    due = session.scalars(
        select(Enterprise).where(
            Enterprise.status.in_([EnterpriseStatus.TRIAL, EnterpriseStatus.ACTIVE])
        )
    ).all()

    frozen_count = 0
    for ent in due:
        if ent.status == EnterpriseStatus.TRIAL and ent.trial_ends_at is not None:
            expired = ent.trial_ends_at <= now
            reason = "试用到期"
        elif ent.status == EnterpriseStatus.ACTIVE and ent.service_ends_at is not None:
            expired = ent.service_ends_at <= now
            reason = "服务到期"
        else:
            continue  # 无截止时刻或非到期，跳过
        if not expired:
            continue
        ent.status = EnterpriseStatus.FROZEN
        ent.frozen_at = now
        ent.freeze_reason = reason
        ent.data_purge_at = now + timedelta(days=_PURGE_AFTER_DAYS)
        frozen_count += 1
    if frozen_count:
        session.commit()
    return frozen_count


def purge_expired(
    session: Session,
    now: datetime | None = None,
    *,
    vector=None,
    storage=None,
    bm25=None,
) -> int:
    """FROZEN 且 data_purge_at 到期 → PURGED，清理业务数据（企业行保留）。

    清理顺序红线（方案 §7，复用删除红线）：Milvus 向量 → chunk 行 → doc 行
    → 存储对象最后。vector/storage/bm25 由 worker 注入（测试注入 Fake）；为
    None 时跳过该侧（仅删 MySQL 行），适配纯 service 层测试。

    幂等：只处理 FROZEN 且 data_purge_at 已到期的企业；PURGED 跳过。
    返回本轮回清理的企业数。
    """
    now = now or _now()
    due = session.scalars(
        select(Enterprise).where(
            Enterprise.status == EnterpriseStatus.FROZEN,
            Enterprise.data_purge_at.isnot(None),
            Enterprise.data_purge_at <= now,
        )
    ).all()

    purged = 0
    for ent in due:
        # 先收集该企业名下所有文档（含 oss_key 供存储删除），再按红线顺序清
        docs = session.scalars(
            select(Document).where(Document.enterprise_id == ent.id)
        ).all()
        doc_ids = [d.id for d in docs]
        # 1. Milvus 向量（先删，杜绝孤儿可搜向量）
        if vector is not None:
            for d in docs:
                vector.delete_by_doc(d.id)
            if bm25 is not None:
                for d in docs:
                    bm25.delete_by_doc(d.id)
        # 2. chunk 行 → doc 行（MySQL，同事务）
        if doc_ids:
            session.execute(
                Chunk.__table__.delete().where(Chunk.document_id.in_(doc_ids))
            )
        session.query(Document).filter(Document.enterprise_id == ent.id).delete(
            synchronize_session=False
        )
        session.query(QaRecord).filter(QaRecord.enterprise_id == ent.id).delete(
            synchronize_session=False
        )
        session.query(App).filter(App.enterprise_id == ent.id).delete(
            synchronize_session=False
        )
        session.query(KnowledgeBase).filter(
            KnowledgeBase.enterprise_id == ent.id
        ).delete(synchronize_session=False)
        ent.status = EnterpriseStatus.PURGED
        purged += 1
        # 3. 存储对象最后（提交后删，失败只留无害孤儿对象，对齐 delete_document）
        if storage is not None:
            for d in docs:
                if d.oss_key:
                    storage.delete(d.oss_key)
                    storage.delete(content_key_for(d.oss_key))
    if purged:
        session.commit()
    return purged


def notify_expiring_soon(session: Session, now: datetime | None = None) -> int:
    """到期前 7 天给企业管理员发通知（复用通知中心）。

    幂等：按「到期前 7 天」窗口判断，若通知中心已有同企业同类型的未读通知
    则跳过（避免每日扫描重复刷屏）。返回本轮回新增的通知数。

    注：v1 无邮件通道，通知落在企业管理员的通知中心；邮件提醒随二期补。
    """
    now = now or _now()
    horizon = now + timedelta(days=_NOTIFY_BEFORE_DAYS)
    due = session.scalars(
        select(Enterprise).where(
            Enterprise.status.in_([EnterpriseStatus.TRIAL, EnterpriseStatus.ACTIVE])
        )
    ).all()

    notified = 0
    for ent in due:
        deadline = ent.trial_ends_at if ent.status == EnterpriseStatus.TRIAL else ent.service_ends_at
        if deadline is None or not (now <= deadline <= horizon):
            continue
        # 幂等去重：该企业已有未读的到期提醒则跳过
        dup = session.scalar(
            select(Notification.id).where(
                Notification.enterprise_id == ent.id,
                Notification.type == NotificationType.ENTERPRISE_EXPIRING,
                Notification.is_read.is_(False),
            )
        )
        if dup is not None:
            continue
        session.add(
            Notification(
                enterprise_id=ent.id,
                type=NotificationType.ENTERPRISE_EXPIRING,
                title=f"企业服务将于 {_days_left(deadline, now)} 天后到期",
                content=f"「{ent.name}」的服务将在 {deadline.date()} 到期，届时转为只读冻结，"
                        f"数据保留 {_PURGE_AFTER_DAYS} 天。请及时充值或联系平台转正。",
                resource_type="enterprise",
                resource_id=ent.id,
            )
        )
        notified += 1
    if notified:
        session.commit()
    return notified


def _days_left(deadline: datetime, now: datetime) -> int:
    return max((deadline - now).days, 1)
