"""平台运营后台 API（M5，挂载 /api/v1/platform/*）。

设计出处《商业化多租户设计方案 2026-11-20》§9：PLATFORM 走独立 /api/v1/platform/*
前缀（运营工作台：企业列表/钱包操作/平台统计），整包 require_platform，与企业
控制台 /api/v1/admin/*（require_enterprise 基座）互不串门。

v1 范围（对齐 scripts/enterprise.py 与 wallet_topup.py 的手工运营能力平移到 API）：
- GET  /enterprises           企业列表
- POST /enterprises           开通企业（试用 + 初始额度）
- POST /enterprises/{id}/activate  转正（试用/冻结 → 正式）
- POST /enterprises/{id}/freeze    冻结（只读）
- POST /enterprises/{id}/topup     充值（累加预算 + 落 TOPUP 流水）
- GET  /enterprises/{id}/wallet    企业钱包余额
- POST /enterprises/{id}/invites   发企业管理员注册码（一次性、限 max_uses）
- GET  /enterprises/{id}/invites   企业注册码列表
- POST /invites/{id}/disable       停用注册码

不覆盖：成员账号明细管理（后移）、平台统计（后续）。这些端点与运营脚本共享同一套
ORM 语义（幂等、累加充值、冻结设 data_purge_at），保证脚本与后台行为一致。
"""
import secrets
from datetime import datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.authz import require_platform
from app.api.envelope import EnvelopeRoute
from app.core.db import get_db
from app.models import (
    AdminUser,
    Enterprise,
    EnterpriseStatus,
    EnterpriseWallet,
    InviteCode,
    WalletTransaction,
    WalletTxnType,
)
from app.schemas import (
    EnterpriseActivate,
    EnterpriseCreate,
    EnterpriseFreeze,
    EnterpriseOut,
    EnterpriseTopup,
    InviteCodeCreate,
    InviteCodeOut,
    WalletOut,
)

router = APIRouter(prefix="/platform", tags=["平台运营"], route_class=EnvelopeRoute)

_PURGE_AFTER_DAYS = 60  # 冻结起算的数据保留天数（对齐 lifecycle.py 清理节奏）


def _get_ent_or_404(db: Session, ent_id: int) -> Enterprise:
    ent = db.get(Enterprise, ent_id)
    if ent is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="企业不存在")
    return ent


def _wallet_of(db: Session, ent_id: int) -> EnterpriseWallet:
    """取企业钱包，不存在则兜底建（对齐 wallet_topup.py 语义）。"""
    wallet = db.scalar(
        select(EnterpriseWallet).where(EnterpriseWallet.enterprise_id == ent_id)
    )
    if wallet is None:
        wallet = EnterpriseWallet(enterprise_id=ent_id)
        db.add(wallet)
        db.flush()
    return wallet


def _wallet_out(ent_id: int, wallet: EnterpriseWallet) -> WalletOut:
    return WalletOut(
        enterprise_id=ent_id,
        budget_cny=float(wallet.budget_cny),
        spent_cny=float(wallet.spent_cny),
        reserved_cny=float(wallet.reserved_cny),
        remaining_cny=float(wallet.budget_cny - wallet.spent_cny - wallet.reserved_cny),
    )


@router.get("/enterprises", response_model=list[EnterpriseOut])
def list_enterprises(
    _user: AdminUser = Depends(require_platform),
    db: Session = Depends(get_db),
) -> list[Enterprise]:
    """企业列表（按 id 升序；含冻结/清理态，运营全量视角）。"""
    return list(db.scalars(select(Enterprise).order_by(Enterprise.id)).all())


@router.post("/enterprises", status_code=status.HTTP_201_CREATED, response_model=EnterpriseOut)
def create_enterprise(
    payload: EnterpriseCreate,
    operator: AdminUser = Depends(require_platform),
    db: Session = Depends(get_db),
) -> Enterprise:
    """开通企业（试用）：建企业 + 建钱包 + 落开通充值流水（审计完整）。"""
    ent = Enterprise(
        name=payload.name,
        status=EnterpriseStatus.TRIAL,
        contact_name=payload.contact_name,
        contact_way=payload.contact_way,
        note=payload.note,
    )
    if payload.trial_days > 0:
        ent.trial_ends_at = datetime.now() + timedelta(days=payload.trial_days)
    db.add(ent)
    db.flush()

    wallet = EnterpriseWallet(enterprise_id=ent.id, budget_cny=Decimal(str(payload.budget_cny)))
    db.add(wallet)
    db.flush()
    db.add(
        WalletTransaction(
            enterprise_id=ent.id,
            type=WalletTxnType.TOPUP,
            amount=Decimal(str(payload.budget_cny)),
            remaining_after=Decimal(str(payload.budget_cny)),
            ref_type="",
            ref_id=None,
            operator=operator.username,
            remark="开通试用额度",
        )
    )
    db.commit()
    db.refresh(ent)
    return ent


@router.post("/enterprises/{ent_id}/activate", response_model=EnterpriseOut)
def activate_enterprise(
    ent_id: int,
    payload: EnterpriseActivate,
    _user: AdminUser = Depends(require_platform),
    db: Session = Depends(get_db),
) -> Enterprise:
    """转正：试用/冻结 → 正式，清冻结字段，设服务截止。"""
    ent = _get_ent_or_404(db, ent_id)
    ent.status = EnterpriseStatus.ACTIVE
    ent.frozen_at = None
    ent.freeze_reason = ""
    ent.data_purge_at = None
    if payload.service_days > 0:
        ent.service_ends_at = datetime.now() + timedelta(days=payload.service_days)
    db.commit()
    db.refresh(ent)
    return ent


@router.post("/enterprises/{ent_id}/freeze", response_model=EnterpriseOut)
def freeze_enterprise(
    ent_id: int,
    payload: EnterpriseFreeze,
    _user: AdminUser = Depends(require_platform),
    db: Session = Depends(get_db),
) -> Enterprise:
    """冻结（只读）：设冻结时间 + 原因 + 数据清理日（now+60 天，对齐 worker 清理节奏）。"""
    ent = _get_ent_or_404(db, ent_id)
    ent.status = EnterpriseStatus.FROZEN
    ent.frozen_at = datetime.now()
    ent.freeze_reason = payload.reason or "人工冻结"
    ent.data_purge_at = datetime.now() + timedelta(days=_PURGE_AFTER_DAYS)
    db.commit()
    db.refresh(ent)
    return ent


@router.post("/enterprises/{ent_id}/topup", response_model=WalletOut)
def topup_enterprise(
    ent_id: int,
    payload: EnterpriseTopup,
    operator: AdminUser = Depends(require_platform),
    db: Session = Depends(get_db),
) -> WalletOut:
    """充值：预算累加（+=），落 TOPUP 流水。"""
    _get_ent_or_404(db, ent_id)  # 企业不存在 404
    wallet = _wallet_of(db, ent_id)
    amount = Decimal(str(payload.amount))
    wallet.budget_cny += amount
    db.flush()
    db.add(
        WalletTransaction(
            enterprise_id=ent_id,
            type=WalletTxnType.TOPUP,
            amount=amount,
            remaining_after=wallet.budget_cny - wallet.spent_cny - wallet.reserved_cny,
            ref_type="",
            ref_id=None,
            operator=operator.username,
            remark=f"后台充值 {amount} 元",
        )
    )
    db.commit()
    db.refresh(wallet)
    return _wallet_out(ent_id, wallet)


@router.get("/enterprises/{ent_id}/wallet", response_model=WalletOut)
def get_enterprise_wallet(
    ent_id: int,
    _user: AdminUser = Depends(require_platform),
    db: Session = Depends(get_db),
) -> WalletOut:
    """企业钱包余额（运营视角，可按 id 查任意企业）。"""
    _get_ent_or_404(db, ent_id)
    wallet = _wallet_of(db, ent_id)
    return _wallet_out(ent_id, wallet)


# ── 企业管理员注册码（M5 补：成员账号管理第一步）──────────────────


def _gen_invite_code() -> str:
    """生成 EVK- 前缀注册码（对齐 scripts/invite.py 格式）。"""
    return "EVK-" + secrets.token_urlsafe(12).upper().replace("-", "").replace("_", "")[:12]


@router.post(
    "/enterprises/{ent_id}/invites",
    status_code=status.HTTP_201_CREATED,
    response_model=InviteCodeOut,
)
def create_invite_code(
    ent_id: int,
    payload: InviteCodeCreate,
    _user: AdminUser = Depends(require_platform),
    db: Session = Depends(get_db),
) -> InviteCode:
    """为企业发企业管理员注册码（一次性、限 max_uses）。

    返回的 code 为明文，仅平台运营可见；凭码注册即成为该企业 ENT_ADMIN（见
    auth.register）。密码由注册者自设，平台无从获得。
    """
    _get_ent_or_404(db, ent_id)
    invite = InviteCode(
        code=_gen_invite_code(),
        enterprise_id=ent_id,
        max_uses=payload.max_uses,
        used_count=0,
        note=payload.note or "",
        enabled=True,
    )
    db.add(invite)
    db.commit()
    db.refresh(invite)
    return invite


@router.get("/enterprises/{ent_id}/invites", response_model=list[InviteCodeOut])
def list_invite_codes(
    ent_id: int,
    _user: AdminUser = Depends(require_platform),
    db: Session = Depends(get_db),
) -> list[InviteCode]:
    """企业注册码列表（含未用/已用/停用，运营全量视角，按 id 降序）。"""
    _get_ent_or_404(db, ent_id)
    return list(
        db.scalars(
            select(InviteCode)
            .where(InviteCode.enterprise_id == ent_id)
            .order_by(InviteCode.id.desc())
        ).all()
    )


@router.post("/invites/{invite_id}/disable", response_model=InviteCodeOut)
def disable_invite_code(
    invite_id: int,
    _user: AdminUser = Depends(require_platform),
    db: Session = Depends(get_db),
) -> InviteCode:
    """停用注册码（已注册账号不受影响）。"""
    invite = db.get(InviteCode, invite_id)
    if invite is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="注册码不存在")
    invite.enabled = False
    db.commit()
    db.refresh(invite)
    return invite
