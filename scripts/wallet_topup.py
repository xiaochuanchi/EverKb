"""企业钱包充值运营脚本（M2）：给企业钱包累加额度并落充值流水。

设计出处《商业化多租户设计方案 2026-11-20》§6：只有企业钱包，全员共享；
v1 人工充值（运营脚本 / 后台操作），套餐与支付集成放二期。

语义：充值 = budget_cny 累加（+= amount），可多次充值；每次落一条 TOPUP
流水（amount 带正号，remaining_after 为充值后剩余额度快照）。

用法（仓库根）：
    .venv/bin/python scripts/wallet_topup.py --enterprise-id 1 --amount 20 --operator ops
    .venv/bin/python scripts/wallet_topup.py --enterprise-id 1 --amount 20 --show  # 充完显示余额
"""
import argparse
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from sqlalchemy import select  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.db import make_engine, make_session_factory  # noqa: E402
from app.models import Enterprise, EnterpriseWallet, WalletTransaction, WalletTxnType  # noqa: E402


def _show_wallet(s, enterprise_id: int) -> None:
    w = s.scalar(
        select(EnterpriseWallet).where(EnterpriseWallet.enterprise_id == enterprise_id)
    )
    if w is None:
        print("  （无钱包记录）")
        return
    remaining = w.budget_cny - w.spent_cny - w.reserved_cny
    print(
        f"  预算 {w.budget_cny} | 已结算 {w.spent_cny} | 在途 {w.reserved_cny} "
        f"| 剩余 {remaining}"
    )


def _main() -> int:
    parser = argparse.ArgumentParser(description="企业钱包充值")
    parser.add_argument("--enterprise-id", type=int, required=True, help="企业 id")
    parser.add_argument("--amount", type=Decimal, required=True, help="充值金额（元），累加到预算")
    parser.add_argument("--operator", default="ops", help="操作者（落流水，默认 ops）")
    parser.add_argument("--show", action="store_true", help="充完显示余额")
    args = parser.parse_args()

    if args.amount <= 0:
        print("错误：充值金额必须大于 0")
        return 1

    engine = make_engine(get_settings().mysql_url)
    EnterpriseWallet.__table__.create(bind=engine, checkfirst=True)
    WalletTransaction.__table__.create(bind=engine, checkfirst=True)

    with make_session_factory(engine)() as s:
        ent = s.get(Enterprise, args.enterprise_id)
        if ent is None:
            print(f"错误：企业 id={args.enterprise_id} 不存在")
            return 1
        wallet = s.scalar(
            select(EnterpriseWallet).where(EnterpriseWallet.enterprise_id == args.enterprise_id)
        )
        if wallet is None:
            wallet = EnterpriseWallet(enterprise_id=args.enterprise_id)
            s.add(wallet)
            s.flush()
        wallet.budget_cny += args.amount
        s.flush()
        remaining = wallet.budget_cny - wallet.spent_cny - wallet.reserved_cny
        s.add(
            WalletTransaction(
                enterprise_id=args.enterprise_id,
                type=WalletTxnType.TOPUP,
                amount=args.amount,
                remaining_after=remaining,
                ref_type="",
                ref_id=None,
                operator=args.operator,
                remark=f"充值 {args.amount} 元",
            )
        )
        s.commit()

    print(f"已为 {ent.name}（id={args.enterprise_id}）充值 {args.amount} 元")
    if args.show:
        with make_session_factory(engine)() as s:
            _show_wallet(s, args.enterprise_id)
    return 0


if __name__ == "__main__":
    sys.exit(_main())
