"""幂等迁移（M1 商业化多租户）：给已有库加租户列 + 建 3 新表 + 存量数据归默认企业。

项目没有 Alembic，init_db() 的 create_all 只建新表、不会给已有表加列，
所以线上库必须跑一次本脚本（重复跑安全）。

用法（仓库根）：
    .venv/bin/python scripts/migrate_tenant.py [--default-enterprise "默认企业"]

执行内容（设计方案 §4.2、§11）：
1. admin_user 补 enterprise_id 列（历史 role='super' → 'platform'）；
2. knowledge_base / document / app / qa_record / trace_span / notification
   各补 enterprise_id 列 + 索引（chunk 不加，经 doc_id 归属）；
3. 建 enterprise / enterprise_wallet / wallet_transaction 三张表（已存在跳过）；
4. 建「默认企业」并把存量数据（enterprise_id 为 NULL 的）归到默认企业——
   默认企业 = 平台自己的企业，存量账号/知识库/文档/应用/记录/Trace/通知全部
   归其名下，保证租户隔离启动时没有「无主」数据。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from sqlalchemy import inspect, select, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.db import make_engine  # noqa: E402
from app.models import (  # noqa: E402
    Enterprise,
    EnterpriseStatus,
    EnterpriseWallet,
    UserRole,
    WalletTransaction,
)

# 需要加 enterprise_id 列的业务表（chunk 除外，经 doc_id 归属，方案 §4.2）
# 注意：invite_code（企业管理员注册码）也必须带 enterprise_id——它是租户隔离的关键，
# 否则 platform 发码/列表接口会查不存在的列（历史遗漏，M5 补邀请码管理时暴露）。
_ENTERPRISE_SCOPED_TABLES = [
    "knowledge_base",
    "document",
    "app",
    "qa_record",
    "trace_span",
    "notification",
    "invite_code",
]

# 需要删除的废弃列（M1 设计删除，但旧库可能还留着；模型已去掉这些字段，
# 若不删，NOT NULL 无默认值的列会导致 INSERT 报错——见 valid_days）。
# 形如 {表名: [废弃列名...]}，按列逐一 DROP（幂等：先查 information_schema）。
_DROPPED_COLUMNS = {
    "invite_code": ["budget_cny", "valid_days", "allowed_app_id"],
}


def _drop_column(conn, table_name: str, column_name: str) -> None:
    """删除废弃列（幂等：MySQL 查 information_schema，SQLite 查 pragma）。"""
    if conn.dialect.name == "mysql":
        exists = conn.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.columns "
                "WHERE table_schema = DATABASE() AND table_name = :t AND column_name = :c"
            ),
            {"t": table_name, "c": column_name},
        ).scalar()
    else:
        exists = conn.execute(
            text(f"PRAGMA table_info('{table_name}')")
        ).mappings().all()
        exists = any(r["name"] == column_name for r in exists)
    if exists:
        conn.execute(text(f"ALTER TABLE {table_name} DROP COLUMN {column_name}"))
        print(f"  {table_name}: 删除废弃列 {column_name}")


def _add_enterprise_id_column(conn, table_name: str) -> None:
    """给指定表补 enterprise_id 列（BIGINT，可空），已存在则跳过。"""
    ddl = "BIGINT NULL"
    # MySQL 与 SQLite 均接受 BIGINT NULL；列注释经 COMMENT 追加（MySQL 专用）
    if conn.dialect.name == "mysql":
        ddl = "BIGINT NULL COMMENT '所属企业 id（NULL=默认企业/平台遗留数据，租户隔离入口）'"
    conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN enterprise_id {ddl}"))


def _ensure_index(conn, table_name: str, index_name: str) -> None:
    """给 enterprise_id 建索引（幂等：先查 information_schema / sqlite_master）。"""
    if conn.dialect.name == "mysql":
        exists = conn.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.statistics "
                "WHERE table_schema = DATABASE() AND table_name = :t AND index_name = :i"
            ),
            {"t": table_name, "i": index_name},
        ).scalar()
    else:
        exists = conn.execute(
            text(
                "SELECT COUNT(*) FROM sqlite_master "
                "WHERE type = 'index' AND tbl_name = :t AND name = :i"
            ),
            {"t": table_name, "i": index_name},
        ).scalar()
    if not exists:
        conn.execute(text(f"CREATE INDEX {index_name} ON {table_name} (enterprise_id)"))


def main() -> int:
    engine = make_engine(get_settings().mysql_url)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())

    if "admin_user" not in tables:
        print("库里还没有 admin_user 表，先执行 init_db / 启动一次后端即可（create_all 会建全）")
        return 1

    with engine.begin() as conn:
        # 1. admin_user 补列 + 历史 super 归一为 platform
        admin_cols = {c["name"] for c in inspector.get_columns("admin_user")}
        if "enterprise_id" not in admin_cols:
            _add_enterprise_id_column(conn, "admin_user")
            _ensure_index(conn, "admin_user", "ix_admin_user_enterprise")
            print("  admin_user: 补 enterprise_id 列 + 索引")
        # 老库可能压根没有 role 列（早于体验账号改造）：先补列，默认 platform。
        # 存量账号都视作平台管理员（无 trial 历史语义）。
        if "role" not in admin_cols:
            role_ddl = "VARCHAR(16) NOT NULL DEFAULT 'platform'"
            if conn.dialect.name == "mysql":
                role_ddl = "VARCHAR(16) NOT NULL DEFAULT 'platform' COMMENT '角色：platform=平台 / ent_admin=企业管理员 / member=成员'"
            conn.execute(text(f"ALTER TABLE admin_user ADD COLUMN role {role_ddl}"))
            print("  admin_user: 补 role 列（默认 platform）")
        else:
            conn.execute(
                text("UPDATE admin_user SET role = :p WHERE role = 'super' OR role IS NULL OR role = ''"),
                {"p": UserRole.PLATFORM},
            )

        # 2. 业务表补列 + 索引
        for t in _ENTERPRISE_SCOPED_TABLES:
            if t not in tables:
                continue  # 表都还没有，等 create_all 建全再跑
            cols = {c["name"] for c in inspector.get_columns(t)}
            if "enterprise_id" not in cols:
                _add_enterprise_id_column(conn, t)
                print(f"  {t}: 补 enterprise_id 列")
            _ensure_index(conn, t, f"ix_{t}_enterprise")

        # 2b. 删除废弃列（M1 设计删除；不删会因 NOT NULL 无默认值导致 INSERT 失败）
        for t, cols_to_drop in _DROPPED_COLUMNS.items():
            if t not in tables:
                continue
            for col in cols_to_drop:
                _drop_column(conn, t, col)

    # 3. 建 3 新表（幂等）
    Enterprise.__table__.create(bind=engine, checkfirst=True)
    EnterpriseWallet.__table__.create(bind=engine, checkfirst=True)
    WalletTransaction.__table__.create(bind=engine, checkfirst=True)
    print("  新表: enterprise / enterprise_wallet / wallet_transaction 已就绪")

    # 4. 建默认企业（走 ORM，让 Python 层 default 生效）+ 归位存量数据
    with Session(engine) as session:
        ent = session.scalar(select(Enterprise).order_by(Enterprise.id).limit(1))
        if ent is None:
            ent = Enterprise(name="默认企业", status=EnterpriseStatus.ACTIVE)
            session.add(ent)
            session.flush()
            session.add(EnterpriseWallet(enterprise_id=ent.id))
            session.flush()
        ent_id = ent.id

        # 存量无主数据归默认企业（admin_user 里 platform 账号保持 NULL = 平台账号）
        session.execute(
            text("UPDATE admin_user SET enterprise_id = :eid WHERE role != :p AND enterprise_id IS NULL"),
            {"eid": ent_id, "p": UserRole.PLATFORM},
        )
        for t in _ENTERPRISE_SCOPED_TABLES:
            if t not in tables:
                continue
            session.execute(
                text(f"UPDATE {t} SET enterprise_id = :eid WHERE enterprise_id IS NULL"),
                {"eid": ent_id},
            )
        session.commit()

    print(f"迁移完成：默认企业 id={ent_id}，存量数据已归位")
    return 0


if __name__ == "__main__":
    sys.exit(main())
