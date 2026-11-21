"""企业生命周期运营脚本（M3）：开通 / 转正 / 冻结 / 列表。

设计出处《商业化多租户设计方案 2026-11-20》§7、§8、§11。v1 人工运营
（平台管理员手动开通/转正/冻结，无支付与套餐表）。充值走独立的
scripts/wallet_topup.py（M2）。

用法（仓库根）：
    .venv/bin/python scripts/enterprise.py create --name "甲公司" --trial-days 7 --budget 20 --seed
    .venv/bin/python scripts/enterprise.py activate --enterprise-id 1 --service-days 365
    .venv/bin/python scripts/enterprise.py freeze --enterprise-id 1 --reason "欠费"
    .venv/bin/python scripts/enterprise.py list

create 即开通试用：建企业（status=TRIAL + trial_ends_at=now+trial-days）+ 建钱包
（budget 额度）。加 --seed 则在开通后联动 scripts/seed_enterprise.py 播种示例 KB
与预配置应用（开箱即用，M4）。转正 activate 设 status=ACTIVE + service_ends_at。
冻结 freeze 设 FROZEN + data_purge_at=now+60 天（对齐生命周期 worker 的清理节奏）。
"""
import argparse
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from sqlalchemy import select  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.db import make_engine, make_session_factory  # noqa: E402
from app.models import (  # noqa: E402
    Enterprise,
    EnterpriseStatus,
    EnterpriseWallet,
    WalletTransaction,
    WalletTxnType,
)

_PURGE_AFTER_DAYS = 60


def _session_factory():
    engine = make_engine(get_settings().mysql_url)
    Enterprise.__table__.create(bind=engine, checkfirst=True)
    EnterpriseWallet.__table__.create(bind=engine, checkfirst=True)
    WalletTransaction.__table__.create(bind=engine, checkfirst=True)
    return make_session_factory(engine)


def _create(args) -> int:
    with _session_factory()() as s:
        ent = Enterprise(name=args.name, status=EnterpriseStatus.TRIAL)
        if args.trial_days > 0:
            ent.trial_ends_at = datetime.now() + timedelta(days=args.trial_days)
        s.add(ent)
        s.flush()
        s.add(EnterpriseWallet(enterprise_id=ent.id, budget_cny=Decimal(args.budget)))
        # 充值流水（首次开通的额度也落一条 TOPUP，审计完整）
        s.add(
            WalletTransaction(
                enterprise_id=ent.id,
                type=WalletTxnType.TOPUP,
                amount=Decimal(args.budget),
                remaining_after=Decimal(args.budget),
                operator=args.operator,
                remark="开通试用额度",
            )
        )
        s.commit()
        ent_id = ent.id
    print(f"已开通企业 {args.name}（id={ent_id}）")
    print(f"  试用 {args.trial_days} 天，额度 {args.budget} 元")

    if args.seed:
        # 联动播种（M4 开箱体验）：示例 KB + 预配置应用，幂等可重跑
        from scripts.seed_enterprise import seed_enterprise as _seed

        settings = get_settings()
        engine = make_engine(settings.mysql_url)
        from app.core.storage import LocalDiskStorage
        from app.services.embedding import create_embedder
        from app.services.vector import create_vector

        storage = LocalDiskStorage(root=settings.storage_root)
        embedder = create_embedder(settings)
        vector = create_vector(settings)
        vector.ensure_collection()
        try:
            from scripts.seed_enterprise import _DEFAULT_SEED_DIR
            seed_dir = args.seed_dir or _DEFAULT_SEED_DIR
            result = _seed(
                make_session_factory(engine),
                enterprise_id=ent_id,
                seed_dir=seed_dir,
                storage=storage, embedder=embedder, vector=vector, settings=settings,
            )
            print(f"  已播种：示例知识库 id={result['kb_id']}，文档 {result['doc_count']} 篇，"
                  f"应用 id={result['app_id']}")
        except Exception as e:
            print(f"  [警告] 播种失败（可稍后重跑 seed_enterprise.py）：{e}")

    print("  下一步：发企业管理员注册码 → scripts/invite.py create --enterprise-id %d" % ent_id)
    return 0


def _activate(args) -> int:
    with _session_factory()() as s:
        ent = s.get(Enterprise, args.enterprise_id)
        if ent is None:
            print(f"错误：企业 id={args.enterprise_id} 不存在")
            return 1
        ent.status = EnterpriseStatus.ACTIVE
        ent.frozen_at = None
        ent.freeze_reason = ""
        ent.data_purge_at = None
        if args.service_days > 0:
            ent.service_ends_at = datetime.now() + timedelta(days=args.service_days)
        s.commit()
    print(f"已转正 {ent.name}（id={args.enterprise_id}），服务至 {ent.service_ends_at.date() if ent.service_ends_at else '长期'}")
    return 0


def _freeze(args) -> int:
    with _session_factory()() as s:
        ent = s.get(Enterprise, args.enterprise_id)
        if ent is None:
            print(f"错误：企业 id={args.enterprise_id} 不存在")
            return 1
        ent.status = EnterpriseStatus.FROZEN
        ent.frozen_at = datetime.now()
        ent.freeze_reason = args.reason or "人工冻结"
        ent.data_purge_at = datetime.now() + timedelta(days=_PURGE_AFTER_DAYS)
        s.commit()
    print(f"已冻结 {ent.name}（id={args.enterprise_id}），数据保留 {_PURGE_AFTER_DAYS} 天后清理")
    return 0


def _list(_args) -> int:
    with _session_factory()() as s:
        rows = s.scalars(select(Enterprise).order_by(Enterprise.id)).all()
        if not rows:
            print("暂无企业")
            return 0
        status_names = {1: "试用", 2: "正式", 3: "冻结", 4: "已清理"}
        for e in rows:
            w = s.scalar(
                select(EnterpriseWallet).where(EnterpriseWallet.enterprise_id == e.id)
            )
            budget = w.budget_cny if w else Decimal("0")
            print(
                f"[{e.id}] {e.name:<16} {status_names.get(e.status, e.status):<4} "
                f"额度={budget}  {e.contact_name} {e.contact_way}"
            )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="企业生命周期运营")
    sub = parser.add_subparsers(dest="cmd", required=True)

    create = sub.add_parser("create", help="开通企业（试用）")
    create.add_argument("--name", required=True, help="企业名")
    create.add_argument("--trial-days", type=int, default=7, help="试用天数（0=不过期）")
    create.add_argument("--budget", type=Decimal, default=Decimal("20"), help="试用额度（元）")
    create.add_argument("--operator", default="ops", help="操作者")
    create.add_argument("--seed", action="store_true", help="开通后联动播种示例 KB 与应用（M4）")
    create.add_argument("--seed-dir", type=Path, default=None, help="种子资源包目录（默认 data/seed）")
    create.set_defaults(func=_create)

    activate = sub.add_parser("activate", help="转正（冻结/试用 → 正式）")
    activate.add_argument("--enterprise-id", type=int, required=True)
    activate.add_argument("--service-days", type=int, default=365, help="服务天数（0=不过期）")
    activate.set_defaults(func=_activate)

    freeze = sub.add_parser("freeze", help="冻结企业（只读）")
    freeze.add_argument("--enterprise-id", type=int, required=True)
    freeze.add_argument("--reason", default="", help="冻结原因")
    freeze.set_defaults(func=_freeze)

    sub.add_parser("list", help="列出企业").set_defaults(func=_list)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
