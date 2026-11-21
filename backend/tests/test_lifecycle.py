"""M3 企业生命周期状态机锁定测试。

设计出处《商业化多租户设计方案 2026-11-20》§7、§11。锁定点：
- 状态跃迁幂等（重复执行不重复冻结/不重复通知）；
- 试用/服务到期转 FROZEN，设 frozen_at + freeze_reason + data_purge_at(+60 天)；
- FROZEN 满 60 天转 PURGED，按删除红线清理业务数据（企业行保留）；
- 到期前 7 天通知幂等（同企业不重复刷屏）；
- 冻结企业问答 403（只读冻结边界）。

红线 3：测试不出网——直接用 SQLite 会话 + Fake 双件套。
"""
from datetime import datetime, timedelta

import pytest

from app.models import (
    App,
    Document,
    Enterprise,
    EnterpriseStatus,
    EnterpriseWallet,
    KnowledgeBase,
    Notification,
    NotificationType,
    QaRecord,
    UserRole,
)
from app.services.lifecycle import (
    _PURGE_AFTER_DAYS,
    notify_expiring_soon,
    purge_expired,
    transition_expired,
)
from app.services.vector import FakeVector
from tests.conftest import seed_admin


@pytest.fixture()
def s(client):
    """SQLite 会话（client 夹具已 init_db 建全表）。"""
    with client.app.state.session_factory() as session:
        yield session


def _ent(session, *, name="企业", status=EnterpriseStatus.TRIAL, trial_ends=None,
         service_ends=None, frozen_at=None, data_purge_at=None, freeze_reason=""):
    ent = Enterprise(name=name, status=status, trial_ends_at=trial_ends,
                     service_ends_at=service_ends, frozen_at=frozen_at,
                     data_purge_at=data_purge_at, freeze_reason=freeze_reason)
    session.add(ent)
    session.commit()
    session.refresh(ent)
    return ent


def _now():
    return datetime(2026, 12, 1, 12, 0, 0)


def test_trial_expiry_transitions_to_frozen(s):
    """试用到期 → FROZEN，设 frozen_at + freeze_reason + data_purge_at。"""
    ent = _ent(s, trial_ends=_now() - timedelta(days=1))
    n = transition_expired(s, now=_now())
    assert n == 1
    s.refresh(ent)
    assert ent.status == EnterpriseStatus.FROZEN
    assert ent.freeze_reason == "试用到期"
    assert ent.frozen_at == _now()
    assert ent.data_purge_at == _now() + timedelta(days=_PURGE_AFTER_DAYS)


def test_active_expiry_transitions_to_frozen(s):
    """正式企业服务到期 → FROZEN。"""
    ent = _ent(s, status=EnterpriseStatus.ACTIVE, service_ends=_now() - timedelta(days=1))
    n = transition_expired(s, now=_now())
    assert n == 1
    s.refresh(ent)
    assert ent.status == EnterpriseStatus.FROZEN
    assert ent.freeze_reason == "服务到期"


def test_transition_idempotent(s):
    """跃迁幂等：已冻结企业重复执行不重复处理。"""
    ent = _ent(s, trial_ends=_now() - timedelta(days=1))
    assert transition_expired(s, now=_now()) == 1
    # 第二次执行：已是 FROZEN，不再处理
    assert transition_expired(s, now=_now()) == 0
    s.refresh(ent)
    assert ent.status == EnterpriseStatus.FROZEN


def test_not_expired_not_transitioned(s):
    """未到期企业不冻结。"""
    ent = _ent(s, trial_ends=_now() + timedelta(days=5))
    assert transition_expired(s, now=_now()) == 0
    s.refresh(ent)
    assert ent.status == EnterpriseStatus.TRIAL


def test_purge_expired_cleans_data_and_marks_purged(s):
    """冻结满 60 天 → PURGED，清理名下业务数据，企业行保留。"""
    ent = _ent(s, status=EnterpriseStatus.FROZEN, frozen_at=_now() - timedelta(days=61),
               data_purge_at=_now() - timedelta(days=1))
    # 造企业名下数据
    kb = KnowledgeBase(name="企业库", enterprise_id=ent.id)
    session_add(s, kb)
    doc = Document(kb_id=kb.id, name="doc", source_type=1, file_type="md",
                   status=6, enabled=True, enterprise_id=ent.id)
    session_add(s, doc)
    app = App(name="企业应用", kb_ids=[], api_key="sk-x", enabled=True, enterprise_id=ent.id)
    session_add(s, app)
    qa = QaRecord(app_id=app.id, enterprise_id=ent.id, user_key="u", question="q",
                  answer="a", grounded=True, chunk_ids=[], doc_ids=[], scores=[],
                  citations=[], model_snapshot={})
    session_add(s, qa)

    vector = FakeVector(dim=8)
    n = purge_expired(s, now=_now(), vector=vector)
    assert n == 1
    s.refresh(ent)
    assert ent.status == EnterpriseStatus.PURGED
    # 业务数据已清
    assert s.query(Document).count() == 0
    assert s.query(QaRecord).count() == 0
    assert s.query(App).count() == 0
    assert s.query(KnowledgeBase).count() == 0
    # 企业行保留
    assert s.get(Enterprise, ent.id) is not None


def test_purge_idempotent(s):
    """清理幂等：PURGED 企业重复执行不再清理。"""
    ent = _ent(s, status=EnterpriseStatus.FROZEN, data_purge_at=_now() - timedelta(days=1))
    assert purge_expired(s, now=_now()) == 1
    assert purge_expired(s, now=_now()) == 0
    s.refresh(ent)
    assert ent.status == EnterpriseStatus.PURGED


def test_purge_not_due_not_cleaned(s):
    """data_purge_at 未到期不清理。"""
    ent = _ent(s, status=EnterpriseStatus.FROZEN, data_purge_at=_now() + timedelta(days=10))
    assert purge_expired(s, now=_now()) == 0
    s.refresh(ent)
    assert ent.status == EnterpriseStatus.FROZEN


def test_notify_expiring_soon_creates_notification(s):
    """到期前 7 天内发通知；同企业幂等不重复。"""
    ent = _ent(s, trial_ends=_now() + timedelta(days=3))  # 3 天后到期，落在 7 天窗口
    n = notify_expiring_soon(s, now=_now())
    assert n == 1
    notif = s.query(Notification).filter_by(enterprise_id=ent.id).one()
    assert notif.type == NotificationType.ENTERPRISE_EXPIRING
    # 幂等：第二次不再新增
    assert notify_expiring_soon(s, now=_now()) == 0
    assert s.query(Notification).filter_by(enterprise_id=ent.id).count() == 1


def test_notify_outside_window_skipped(s):
    """超出 7 天窗口不通知。"""
    _ent(s, trial_ends=_now() + timedelta(days=30))
    assert notify_expiring_soon(s, now=_now()) == 0


def test_frozen_enterprise_assistant_chat_403(client):
    """冻结企业：后台问答 403（只读冻结边界，零成本拦截）。"""
    session = client.app.state.session_factory()
    ent = Enterprise(name="冻结企业", status=EnterpriseStatus.FROZEN)
    session.add(ent)
    session.flush()
    session.add(EnterpriseWallet(enterprise_id=ent.id, budget_cny=10, spent_cny=0, reserved_cny=0))
    app = App(name="冻结应用", kb_ids=[], api_key="sk-f", enabled=True, enterprise_id=ent.id)
    session.add(app)
    session.commit()
    ent_id = ent.id
    app_id = app.id
    session.close()

    ent_admin = seed_admin(client.app, username="ent_admin_frozen", password="test1234",
                           role=UserRole.ENT_ADMIN, enterprise_id=ent_id)
    from app.core.security import create_access_token
    client.headers["Authorization"] = f"Bearer {create_access_token(ent_admin.id, client.app.state.settings)}"

    r = client.post("/api/v1/admin/assistant/chat", json={"app_id": app_id, "question": "x"})
    assert r.status_code == 403


def session_add(session, obj):
    """helper：add + flush，拿到自增 id。"""
    session.add(obj)
    session.flush()
    return obj
