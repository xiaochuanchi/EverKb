"""首账号 seed（Task 14）：创建平台第一个 PLATFORM 账号 + 默认企业。

手动执行（仓库根）：`python3 scripts/seed_admin.py`，交互式输入密码；
或 `python3 scripts/seed_admin.py --username ops --password 'S3cret!xx'`。

行为：库中已存在任何账号时拒绝创建（防覆盖/重复 seed）——多账号管理
一期不做，改密走管理后台 user-center（PUT /api/v1/admin/auth/password）。

M1 商业化多租户：首个账号为 PLATFORM（平台管理员），同时创建「默认企业」
（存量数据归位用），platform 账号不绑企业（enterprise_id 保持 NULL）。
"""
import argparse
import getpass
import sys
from pathlib import Path

# 脚本位于仓库根 scripts/，app 包在 backend/ 下：锚定后任意工作目录可执行
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from sqlalchemy import func, select  # noqa: E402

from app.core.db import init_db, make_engine, make_session_factory  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models import AdminUser, Enterprise, EnterpriseStatus, UserRole  # noqa: E402


def _main() -> int:
    parser = argparse.ArgumentParser(description="创建管理后台首账号")
    parser.add_argument("--username", help="登录名（不传则交互输入）")
    parser.add_argument("--password", help="密码（不传则交互输入，不回显）")
    args = parser.parse_args()

    username = args.username or input("登录名: ").strip()
    if not username:
        print("错误：登录名不能为空")
        return 1
    password = args.password or getpass.getpass("密码: ")
    if len(password) < 8:
        print("错误：密码至少 8 位")
        return 1

    from app.core.config import get_settings

    engine = make_engine(get_settings().mysql_url)
    init_db(engine)
    with make_session_factory(engine)() as session:
        existing = session.scalar(select(func.count()).select_from(AdminUser))
        if existing:
            print(f"错误：库中已有 {existing} 个账号，拒绝重复 seed（改密请走管理后台）")
            return 1
        # 默认企业：存量数据归位 + 后续企业侧隔离的锚点
        ent = session.scalar(select(Enterprise).order_by(Enterprise.id).limit(1))
        if ent is None:
            ent = Enterprise(name="默认企业", status=EnterpriseStatus.ACTIVE)
            session.add(ent)
            session.flush()
        session.add(
            AdminUser(
                username=username,
                password_hash=hash_password(password),
                role=UserRole.PLATFORM,
                enterprise_id=None,  # 平台账号不绑企业
            )
        )
        session.commit()
    print(f"已创建平台管理员 {username}（默认企业 id={ent.id}），可用其登录 /api/v1/admin/auth/login")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
