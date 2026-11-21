"""企业管理员注册码运营脚本（M1）：创建 / 查看 / 停用。

平台管理员为企业开通试用后，用本脚本发企业管理员注册码（绑定 enterprise_id），
体验者凭码注册即 ENT_ADMIN，落到企业控制台（设计方案 §8）。

企业账号开通（建企业 + 设钱包额度）见 scripts/enterprise.py（M4 开箱体验前先
手动执行）；本脚本只负责发码。先跑 scripts/migrate_tenant.py，再用本脚本发码。

用法（仓库根）：
    .venv/bin/python scripts/invite.py create --enterprise-id 1 --uses 1 --note "给张三"
    .venv/bin/python scripts/invite.py list
    .venv/bin/python scripts/invite.py disable EVK-XXXXXXXXXXXX
"""
import argparse
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from sqlalchemy import select  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.db import make_engine, make_session_factory  # noqa: E402
from app.models import Enterprise, InviteCode  # noqa: E402


def _session_factory():
    engine = make_engine(get_settings().mysql_url)
    InviteCode.__table__.create(bind=engine, checkfirst=True)  # 兜底：新库直接可用
    return make_session_factory(engine)


def _create(args) -> int:
    code = "EVK-" + secrets.token_urlsafe(12).upper().replace("-", "").replace("_", "")[:12]
    with _session_factory()() as s:
        ent = s.get(Enterprise, args.enterprise_id)
        if ent is None:
            print(f"错误：企业 id={args.enterprise_id} 不存在（先跑 scripts/enterprise.py 建企业）")
            return 1
        invite = InviteCode(
            code=code,
            enterprise_id=args.enterprise_id,
            max_uses=args.uses,
            used_count=0,
            note=args.note or "",
            enabled=True,
        )
        s.add(invite)
        s.commit()
    print(f"注册码: {code}")
    print(f"  绑定企业: {ent.name}（id={args.enterprise_id}），可注册 {args.uses} 个企业管理员")
    print("发给体验者，在注册页填入即可（注册即成为该企业的企业管理员）")
    return 0


def _list(_args) -> int:
    with _session_factory()() as s:
        rows = s.scalars(select(InviteCode).order_by(InviteCode.id.desc()).limit(50)).all()
        if not rows:
            print("暂无注册码")
            return 0
        for r in rows:
            ent_name = s.get(Enterprise, r.enterprise_id).name if r.enterprise_id else "（未绑定）"
            print(
                f"{r.code:<20} 企业={ent_name} 已用{r.used_count}/{r.max_uses} "
                f"{'启用' if r.enabled else '停用'} {r.note}"
            )
    return 0


def _disable(args) -> int:
    with _session_factory()() as s:
        invite = s.scalar(select(InviteCode).where(InviteCode.code == args.code))
        if invite is None:
            print("注册码不存在")
            return 1
        invite.enabled = False
        s.commit()
    print(f"已停用 {args.code}；已注册的账号不受影响（如需停用账号请改 is_active）")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="企业管理员注册码管理")
    sub = parser.add_subparsers(dest="cmd", required=True)

    create = sub.add_parser("create", help="创建企业管理员注册码")
    create.add_argument("--enterprise-id", type=int, required=True, help="绑定的企业 id")
    create.add_argument("--uses", type=int, default=1, help="最多注册几个企业管理员")
    create.add_argument("--note", default="", help="备注，例如发给谁")
    create.set_defaults(func=_create)

    sub.add_parser("list", help="列出注册码").set_defaults(func=_list)

    disable = sub.add_parser("disable", help="停用注册码")
    disable.add_argument("code")
    disable.set_defaults(func=_disable)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
