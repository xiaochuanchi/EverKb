"""企业钱包查询 API（M2，挂载 /api/v1/admin/wallet）。

设计出处《商业化多租户设计方案 2026-11-20》§6、§11：只有企业钱包、全员共享；
企业管理员在此查看余额（budget / spent / reserved / remaining）。充值走运营
脚本 scripts/wallet_topup.py（v1 无支付，人工充值）。

鉴权：require_admin（身份认证）+ 账号须绑企业（enterprise_id 非 NULL）。
平台账号无企业钱包，返回 403（不是 404，避免暴露企业存在性）。
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import require_admin
from app.api.envelope import EnvelopeRoute
from app.core.db import get_db
from app.models import AdminUser, EnterpriseWallet
from app.schemas import WalletOut

router = APIRouter(prefix="/wallet", tags=["钱包"], route_class=EnvelopeRoute)


@router.get("", response_model=WalletOut)
def get_wallet(
    user: AdminUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> WalletOut:
    """当前企业钱包余额。企业管理员可查本企业；平台账号无企业钱包。"""
    if user.enterprise_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="平台账号无企业钱包")
    wallet = db.scalar(
        select(EnterpriseWallet).where(EnterpriseWallet.enterprise_id == user.enterprise_id)
    )
    if wallet is None:
        # 企业尚无钱包行（理论上 migrate 会建默认企业钱包，防御性兜底为空）
        return WalletOut(
            enterprise_id=user.enterprise_id,
            budget_cny=0.0,
            spent_cny=0.0,
            reserved_cny=0.0,
            remaining_cny=0.0,
        )
    return WalletOut(
        enterprise_id=user.enterprise_id,
        budget_cny=float(wallet.budget_cny),
        spent_cny=float(wallet.spent_cny),
        reserved_cny=float(wallet.reserved_cny),
        remaining_cny=float(wallet.budget_cny - wallet.spent_cny - wallet.reserved_cny),
    )
