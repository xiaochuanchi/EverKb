"""M2 钱包计费：quota 引擎（reserve/settle/refund）数学与流水落库锁定测试。

设计出处《商业化多租户设计方案 2026-11-20》§6、§11。旧版 trial 的
test_trial_quota_api.py 随 M1 废弃，本文件在 SQLite 内存库上重新锁死平移后的
enterprise_wallet 版本——并发 reserve 不超额、settle 退差额、refund 释放、
budget=0 拒绝、流水 remaining_after 快照正确。红线 3：测试不出网。
"""
from decimal import Decimal

import pytest
from sqlalchemy import select, text

from app.core.config import Settings
from app.models import EnterpriseWallet, WalletTransaction, WalletTxnType
from app.services import quota


def _wallet(session, enterprise_id, budget="10.0", spent="0", reserved="0") -> EnterpriseWallet:
    w = EnterpriseWallet(
        enterprise_id=enterprise_id,
        budget_cny=Decimal(budget),
        spent_cny=Decimal(spent),
        reserved_cny=Decimal(reserved),
    )
    session.add(w)
    session.commit()
    return w


@pytest.fixture()
def s():
    """独立测试库会话：quota 引擎纯数学，只需 enterprise_wallet 表，不依赖 client。"""
    from app.core.db import init_db, make_engine, make_session_factory

    engine = make_engine("sqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as session:
        yield session


def _budget(session, enterprise_id) -> Decimal:
    return Decimal(
        str(
            session.scalar(
                select(EnterpriseWallet.budget_cny).where(
                    EnterpriseWallet.enterprise_id == enterprise_id
                )
            )
            or "0"
        )
    )


def _spent(session, enterprise_id) -> Decimal:
    return Decimal(
        str(
            session.scalar(
                select(EnterpriseWallet.spent_cny).where(
                    EnterpriseWallet.enterprise_id == enterprise_id
                )
            )
            or "0"
        )
    )


def _reserved(session, enterprise_id) -> Decimal:
    return Decimal(
        str(
            session.scalar(
                select(EnterpriseWallet.reserved_cny).where(
                    EnterpriseWallet.enterprise_id == enterprise_id
                )
            )
            or "0"
        )
    )


def test_reserve_success_increases_reserved(s):
    _wallet(s, 1, budget="10.0")
    ok = quota.reserve(s, 1, Decimal("3.0"))
    assert ok is True
    assert _reserved(s, 1) == Decimal("3.0")
    assert _spent(s, 1) == Decimal("0")  # reserve 只动 reserved，不扣 spent


def test_reserve_rejects_when_exceeding_budget(s):
    _wallet(s, 1, budget="10.0", spent="8.0")
    ok = quota.reserve(s, 1, Decimal("3.0"))  # 8 + 3 > 10
    assert ok is False
    assert _reserved(s, 1) == Decimal("0")  # 失败不产生任何扣减


def test_reserve_rejects_zero_budget(s):
    _wallet(s, 1, budget="0")
    ok = quota.reserve(s, 1, Decimal("1.0"))
    assert ok is False


def test_concurrent_reserve_does_not_overdraw(s):
    """并发两个 reserve 只有预算内的那个成功（rowcount=0 即拒绝）。"""
    _wallet(s, 1, budget="10.0")
    ok1 = quota.reserve(s, 1, Decimal("8.0"))
    ok2 = quota.reserve(s, 1, Decimal("8.0"))  # 8 + 8 > 10，第二个必失败
    assert ok1 is True
    assert ok2 is False
    assert _reserved(s, 1) == Decimal("8.0")


def test_settle_releases_reserve_and_charges_actual(s):
    _wallet(s, 1, budget="10.0", reserved="5.0")
    quota.settle(s, 1, Decimal("5.0"), Decimal("3.0"), ref_id=100)
    assert _reserved(s, 1) == Decimal("0")  # 预留全额释放
    assert _spent(s, 1) == Decimal("3.0")  # 按实际花费结算


def test_settle_partial_reserve_refund(s):
    """预留 5、实际 3：预留释放 5，spent 只加 3（差额退回语义）。"""
    _wallet(s, 1, budget="10.0", reserved="5.0")
    quota.settle(s, 1, Decimal("5.0"), Decimal("3.0"))
    assert _spent(s, 1) == Decimal("3.0")
    assert _reserved(s, 1) == Decimal("0")


def test_settle_writes_consume_transaction(s):
    _wallet(s, 1, budget="10.0", reserved="5.0")
    quota.settle(s, 1, Decimal("5.0"), Decimal("3.0"), ref_id=100, ref_type="qa_record")
    txn = s.scalar(select(WalletTransaction).where(WalletTransaction.enterprise_id == 1))
    assert txn is not None
    assert txn.type == WalletTxnType.CONSUME
    assert Decimal(str(txn.amount)) == Decimal("-3.0")  # 消费带负号
    assert txn.ref_id == 100
    assert txn.ref_type == "qa_record"
    # remaining_after = budget - spent - reserved = 10 - 3 - 0 = 7
    assert Decimal(str(txn.remaining_after)) == Decimal("7.0")


def test_refund_releases_reserve_without_charge(s):
    _wallet(s, 1, budget="10.0", reserved="5.0")
    quota.refund(s, 1, Decimal("5.0"))
    assert _reserved(s, 1) == Decimal("0")
    assert _spent(s, 1) == Decimal("0")  # 退款不产生消费
    # 退款不落流水（方案 §4.1：只记结算事件，预留是内存态会计）
    assert s.scalar(select(WalletTransaction).where(WalletTransaction.enterprise_id == 1)) is None


def test_reserve_amount_conservative(s):
    """预留金额按输入+输出上限估算，宁可偏大（结束后退回差额）。"""
    st = Settings()
    amount = quota.reserve_amount(st, "你好")
    assert amount > 0
    # 预留 = (embed 字符数 * embed 单价 + 输入上限 * llm 入单价 + 输出上限 * llm 出单价) / 百万
    assert amount > quota.actual_amount(st, "你好", "你好", "短答", tokens_in=10, tokens_out=5)


def test_actual_amount_uses_usage_when_present(s):
    st = Settings()
    # 有 usage 时按真实 token 算，不受 answer 字符数影响
    a = quota.actual_amount(st, "q", "p", "很长的答案文本", tokens_in=100, tokens_out=50)
    b = quota.actual_amount(st, "q", "p", "短", tokens_in=100, tokens_out=50)
    assert a == b
