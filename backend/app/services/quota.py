"""企业钱包 token 额度：预估预留 → 流结束后按真实 usage 结算。

设计出处：《商业化多租户设计方案 2026-11-20》§6。旧版 trial 的 quota.py
（admin_user 额度列 + trial 角色）在 M1 已废弃，本模块将其 reserve/settle/
refund 数学**平移**到 enterprise_wallet——原子 UPDATE、预算充足才扣、结算退差额
的语义一字不动，只是钱包行从 admin_user 挪到 enterprise_wallet（§10「平移」）。

设计要点（与旧版一致）：
1. 流式回答的费用只有结束后才知道，因此先按「输入上限 + 输出上限」预留，
   结束按服务商返回的 usage 结算并退回差额——不会因中间态超预算；
2. 预留用单条 UPDATE ... WHERE 预算充足 的原子语句完成，并发请求下由数据库
   行锁保证不会同时超额（rowcount=0 即拒绝）；
3. 单价来自 Settings（元/百万 token），默认保守估算；厂商未回 usage 时按
   prompt/答案字符数估算 token，保证仍能扣费。

M1 仅平移引擎（本模块有测试覆盖、无调用方），M2 在 assistant + open 双入口接线。
"""
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import EnterpriseWallet, WalletTransaction, WalletTxnType

_MILLION = Decimal("1000000")
_CENT = Decimal("0.000001")


def _dec(value) -> Decimal:
    """Numeric 在 SQLite 下可能是 float，统一经 str 转 Decimal 避免二进制误差。"""
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def _price(value: float) -> Decimal:
    return _dec(value)


def estimate_embedding_tokens(text_value: str) -> int:
    """中文约 1 字/token、英文约 4 字符/token；用字符数作保守上限。"""
    return len(text_value or "")


def reserve_amount(settings: Settings, question: str) -> Decimal:
    """问答开始前预留的金额（元）。宁可偏大，结束后按实际退回。"""
    embed = _dec(estimate_embedding_tokens(question)) * _price(settings.embedding_price_cny_per_million)
    llm = (
        _dec(settings.trial_reserve_input_tokens) * _price(settings.llm_price_in_cny_per_million)
        + _dec(settings.trial_reserve_output_tokens) * _price(settings.llm_price_out_cny_per_million)
    )
    return ((embed + llm) / _MILLION).quantize(_CENT, rounding=ROUND_HALF_UP)


def actual_amount(
    settings: Settings,
    question: str,
    prompt: str,
    answer: str,
    tokens_in: int = 0,
    tokens_out: int = 0,
) -> Decimal:
    """结束后按 usage 结算；usage 为 0 时按字符数估算 token。"""
    tin = int(tokens_in or 0) or len(prompt or "")
    tout = int(tokens_out or 0) or len(answer or "")
    embed_tokens = estimate_embedding_tokens(question)
    cost = (
        _dec(tin) * _price(settings.llm_price_in_cny_per_million)
        + _dec(tout) * _price(settings.llm_price_out_cny_per_million)
        + _dec(embed_tokens) * _price(settings.embedding_price_cny_per_million)
    )
    return (cost / _MILLION).quantize(_CENT, rounding=ROUND_HALF_UP)


def reserve(db: Session, enterprise_id: int, amount: Decimal) -> bool:
    """原子预留；预算不足 / 额度为 0 时返回 False，不产生任何扣减。"""
    if amount <= 0:
        return True
    result = db.execute(
        text(
            """
            UPDATE enterprise_wallet
               SET reserved_cny = COALESCE(reserved_cny, 0) + :amount
             WHERE enterprise_id = :ent_id
               AND COALESCE(budget_cny, 0) > 0
               AND COALESCE(spent_cny, 0) + COALESCE(reserved_cny, 0) + :amount
                   <= COALESCE(budget_cny, 0)
            """
        ),
        {"amount": float(amount), "ent_id": enterprise_id},
    )
    db.commit()
    return result.rowcount == 1


def settle(
    db: Session,
    enterprise_id: int,
    reserved: Decimal,
    actual: Decimal,
    *,
    ref_id: int | None = None,
    ref_type: str = "qa_record",
    operator: str = "system",
) -> None:
    """结算：释放预留并按实际花费累加；超额部分不扣（预算硬上限）。

    结算后落一条 CONSUME 流水（amount 带负号，remaining_after 为记账后剩余
    额度快照）。流水只记结算事实，在途预留不落流水（方案 §4.1）。
    """
    db.execute(
        text(
            """
            UPDATE enterprise_wallet
               SET reserved_cny = CASE
                     WHEN COALESCE(reserved_cny, 0) - :reserved < 0 THEN 0
                     ELSE COALESCE(reserved_cny, 0) - :reserved END,
                   spent_cny = COALESCE(spent_cny, 0) + :actual
             WHERE enterprise_id = :ent_id
            """
        ),
        {"reserved": float(reserved), "actual": float(actual), "ent_id": enterprise_id},
    )
    wallet = db.scalar(
        select(EnterpriseWallet).where(EnterpriseWallet.enterprise_id == enterprise_id)
    )
    remaining = _dec(wallet.budget_cny) - _dec(wallet.spent_cny) - _dec(wallet.reserved_cny)
    db.add(
        WalletTransaction(
            enterprise_id=enterprise_id,
            type=WalletTxnType.CONSUME,
            amount=-_dec(actual),
            remaining_after=remaining,
            ref_type=ref_type,
            ref_id=ref_id,
            operator=operator,
        )
    )
    db.commit()


def refund(db: Session, enterprise_id: int, reserved: Decimal) -> None:
    """问答失败时释放预留，不扣费。"""
    db.execute(
        text(
            """
            UPDATE enterprise_wallet
               SET reserved_cny = CASE
                     WHEN COALESCE(reserved_cny, 0) - :reserved < 0 THEN 0
                     ELSE COALESCE(reserved_cny, 0) - :reserved END
             WHERE enterprise_id = :ent_id
            """
        ),
        {"reserved": float(reserved), "ent_id": enterprise_id},
    )
    db.commit()
