"""商业化多租户授权（M1）：三级 fail-closed 依赖 + 统一租户查询入口。

设计出处：《商业化多租户设计方案 2026-11-20》§5。旧版 trial 白名单只回答
「这个角色能走哪些 URL」，回答不了「能操作谁家的资源」。商业化授权分两层：

1. 角色层（能做什么）——三级 fail-closed 依赖，对齐旧 require_admin 的收紧思路：
   - require_platform  运营后台：仅 PLATFORM；
   - require_ent_admin 企业控制台管理动作：ENT_ADMIN（PLATFORM 不降级，运营走独立路由）；
   - require_member    成员白名单（预留，v1 不挂载，随成员账号体系后移）；
   - require_enterprise 企业侧公共基座：v1 仅 ENT_ADMIN，验企业状态（冻结拦截见 §7）。
2. 归属层（能对谁做）——每个涉及租户资源的查询/变更必须过统一入口，禁止散落手写：
   - scoped(db, Model, ent_id)      列表查询自动带 enterprise_id 过滤；
   - ensure_owned(db, obj, ent_id)  单对象校验，不匹配即 404（非 403，不泄露存在性）。

一句话纪律：越权零信任。漏配授权依赖时最坏是「权限偏严」而非越权。
"""
from typing import Type, TypeVar

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import require_admin
from app.models import AdminUser, Enterprise, EnterpriseStatus, UserRole

# ── 角色层（能做什么）──────────────────────────────────────────


def _require_role(user: AdminUser, allowed: set[str], detail: str) -> AdminUser:
    """角色收紧的公共内核：不在允许集即 403（fail-closed）。"""
    if user.role not in allowed:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=detail)
    return user


def require_platform(user: AdminUser = Depends(require_admin)) -> AdminUser:
    """运营后台鉴权：仅 PLATFORM（平台管理员）。

    不降级：企业管理员/成员一律 403。运营走独立 /api/v1/platform/* 路由。
    """
    return _require_role(user, {UserRole.PLATFORM}, "仅平台管理员可访问")


def require_ent_admin(user: AdminUser = Depends(require_admin)) -> AdminUser:
    """企业控制台管理动作：仅 ENT_ADMIN。PLATFORM 不降级（运营走独立路由）。"""
    return _require_role(user, {UserRole.ENT_ADMIN}, "仅企业管理员可操作")


def require_enterprise(user: AdminUser = Depends(require_admin)) -> AdminUser:
    """企业侧公共基座：v1 仅 ENT_ADMIN（成员接入后共用），并验企业绑定。

    冻结拦截（§7）：企业 FROZEN/PURGED 时企业侧问答/管理一律 403，
    但登录、浏览 KB/文档/记录/Trace/钱包等只读动作由上层决定是否放行
    （此处只做角色 + 企业绑定校验，冻结拦截由 ensure_enterprise_active 在
    具体端点按需叠加）。
    """
    if user.role not in {UserRole.ENT_ADMIN, UserRole.MEMBER}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="仅企业账号可访问")
    if user.enterprise_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="账号未绑定企业")
    return user


def require_member(user: AdminUser = Depends(require_admin)) -> AdminUser:
    """成员白名单：问答 / 自己的记录 / KB 浏览（fail-closed）。

    随成员账号体系后移，v1 不挂载——定义在此仅为数据模型与鉴权预留位（§5）。
    """
    return _require_role(user, {UserRole.MEMBER}, "仅企业成员可访问")


# ── 归属层（能对谁做）──────────────────────────────────────────

_ModelT = TypeVar("_ModelT")


def scoped(db: Session, model: Type[_ModelT], ent_id: int):
    """列表查询统一入口：返回已带 enterprise_id 过滤的 select 语句。

    用法：`rows = db.scalars(scoped(db, KnowledgeBase, ent_id).order_by(...)).all()`
    禁止在路由里手写 `.where(Model.enterprise_id == ent_id)` 散落过滤。
    """
    return select(model).where(model.enterprise_id == ent_id)


def ensure_owned(db: Session, obj, ent_id: int) -> None:
    """单对象归属校验：对象不属于 ent_id 即 404（非 403，不泄露存在性）。

    用法：`kb = db.get(KnowledgeBase, kb_id)` 后 `ensure_owned(db, kb, ent_id)`。
    None 对象（不存在）同样 404，与「不属于」统一措辞，杜绝越权探测。
    """
    if obj is None or getattr(obj, "enterprise_id", None) != ent_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="资源不存在")


def ensure_enterprise_active(db: Session, ent_id: int) -> Enterprise:
    """企业状态校验：存在且非冻结/清理，否则 403。

    open 侧计费入口（M2）与企业侧问答挂本依赖——冻结企业一律 403，不触
    embedding/LLM，零成本拦截（§7 只读冻结边界）。
    """
    ent = db.get(Enterprise, ent_id)
    if ent is None or ent.status in (EnterpriseStatus.FROZEN, EnterpriseStatus.PURGED):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="企业服务已冻结，请联系平台")
    return ent
