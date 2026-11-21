"""商业化多租户（M1）越权矩阵锁定测试：三级鉴权依赖 + 统一租户查询入口。

锁定点（设计方案 §5「越权零信任」）：
- 角色层：require_platform 仅 PLATFORM；require_ent_admin 仅 ENT_ADMIN；
  require_enterprise 仅企业账号且必须绑企业；require_member 仅 MEMBER；
  PLATFORM 不降级走企业侧（运营走独立路由）。
- 归属层：scoped 自动带 enterprise_id 过滤；ensure_owned 不匹配即 404
  （非 403，不泄露存在性）；None 对象同样 404。
- ensure_enterprise_active 冻结/清理企业 403。

红线 3：全程 SQLite 内存库 + Fake，不触网。
"""
import pytest
from fastapi import Depends, HTTPException

from app.api.authz import (
    ensure_enterprise_active,
    ensure_owned,
    require_ent_admin,
    require_enterprise,
    require_member,
    require_platform,
    scoped,
)
from app.core.db import init_db, make_engine, make_session_factory
from app.models import (
    AdminUser,
    Enterprise,
    EnterpriseStatus,
    KnowledgeBase,
    UserRole,
)


def _make_user(role, enterprise_id=1):
    return AdminUser(
        username=f"u-{role}-{enterprise_id}",
        password_hash="x",
        role=role,
        enterprise_id=enterprise_id,
    )


@pytest.fixture()
def session():
    engine = make_engine("sqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        yield s


# ── 角色层：fail-closed ──────────────────────────────────────────


@pytest.mark.parametrize(
    "dep,allowed_role,blocked_roles",
    [
        (require_platform, UserRole.PLATFORM, [UserRole.ENT_ADMIN, UserRole.MEMBER]),
        (require_ent_admin, UserRole.ENT_ADMIN, [UserRole.PLATFORM, UserRole.MEMBER]),
        (require_member, UserRole.MEMBER, [UserRole.PLATFORM, UserRole.ENT_ADMIN]),
    ],
)
def test_role_deps_fail_closed(dep, allowed_role, blocked_roles):
    """角色依赖：仅允许的角色放行，其余一律 403（PLATFORM 不降级走企业侧）。"""
    # 允许的角色放行
    assert dep(_make_user(allowed_role)) is not None
    # 其余角色 403
    for role in blocked_roles:
        with pytest.raises(HTTPException) as exc:
            dep(_make_user(role))
        assert exc.value.status_code == 403


def test_require_enterprise_requires_bound_enterprise():
    """企业侧基座：非企业角色 403；企业角色但未绑企业 403。"""
    # 平台账号不能走企业侧（不降级）
    with pytest.raises(HTTPException) as exc:
        require_enterprise(_make_user(UserRole.PLATFORM))
    assert exc.value.status_code == 403
    # 企业管理员但 enterprise_id 为 None 也不放行
    with pytest.raises(HTTPException) as exc:
        require_enterprise(_make_user(UserRole.ENT_ADMIN, enterprise_id=None))
    assert exc.value.status_code == 403


# ── 归属层：scoped / ensure_owned ────────────────────────────────


def test_scoped_filters_by_enterprise(session):
    """scoped：列表查询自动带 enterprise_id 过滤，不泄露他企业数据。"""
    session.add_all(
        [
            KnowledgeBase(name="企业A的库", enterprise_id=1),
            KnowledgeBase(name="企业B的库", enterprise_id=2),
        ]
    )
    session.commit()

    rows = session.scalars(scoped(session, KnowledgeBase, 1)).all()
    assert [r.name for r in rows] == ["企业A的库"]

    rows = session.scalars(scoped(session, KnowledgeBase, 2)).all()
    assert [r.name for r in rows] == ["企业B的库"]


def test_ensure_owned_returns_404_for_foreign_resource(session):
    """ensure_owned：不属于本企业的资源 404（非 403，不泄露存在性）。"""
    kb = KnowledgeBase(name="别人的库", enterprise_id=2)
    session.add(kb)
    session.commit()

    with pytest.raises(HTTPException) as exc:
        ensure_owned(session, kb, 1)
    assert exc.value.status_code == 404


def test_ensure_owned_returns_404_for_missing(session):
    """ensure_owned：None 对象（不存在）同样 404，与「不属于」统一措辞。"""
    with pytest.raises(HTTPException) as exc:
        ensure_owned(session, None, 1)
    assert exc.value.status_code == 404


def test_ensure_owned_passes_for_owned_resource(session):
    kb = KnowledgeBase(name="自家的库", enterprise_id=1)
    session.add(kb)
    session.commit()
    ensure_owned(session, kb, 1)  # 不抛即通过


# ── 企业状态：冻结拦截 ───────────────────────────────────────────


def test_ensure_enterprise_active_blocks_frozen(session):
    """冻结/清理企业 403（只读冻结边界：不触 embedding/LLM，零成本拦截）。"""
    ent = Enterprise(name="冻结企业", status=EnterpriseStatus.FROZEN)
    session.add(ent)
    session.commit()

    with pytest.raises(HTTPException) as exc:
        ensure_enterprise_active(session, ent.id)
    assert exc.value.status_code == 403


def test_ensure_enterprise_active_blocks_purged(session):
    ent = Enterprise(name="清理企业", status=EnterpriseStatus.PURGED)
    session.add(ent)
    session.commit()

    with pytest.raises(HTTPException) as exc:
        ensure_enterprise_active(session, ent.id)
    assert exc.value.status_code == 403


def test_ensure_enterprise_active_passes_active(session):
    ent = Enterprise(name="正式企业", status=EnterpriseStatus.ACTIVE)
    session.add(ent)
    session.commit()

    assert ensure_enterprise_active(session, ent.id) is ent
