"""Task 2 验收：7 张表建表 + 全链路插入默认值 + 讨论决策的行为锁定。

SQLite 内存库（红线 3：测试不出网）。真实 MySQL 建表验证走
`docker exec everkb-mysql mysql ... SHOW TABLES`（infra plan I4）。
"""
import pytest
from datetime import datetime, timedelta
from sqlalchemy import inspect
from sqlalchemy.dialects import mysql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.schema import CreateTable

from app import models
from app.core.db import Base, init_db, make_engine, make_session_factory
from app.models import AdminUser, App, Chunk, Document, KnowledgeBase, QaRecord, TraceSpan

ALL_TABLES = {
    "admin_user",
    "knowledge_base",
    "app",
    "document",
    "chunk",
    "qa_record",
    "trace_span",
}


@pytest.fixture()
def session():
    engine = make_engine("sqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        yield s


def test_create_all_seven_tables(session):
    names = set(inspect(session.get_bind()).get_table_names())
    assert names == ALL_TABLES


def test_full_chain_insert_and_defaults(session):
    """kb → document → chunk → app → qa_record → trace_span 全链路 + 默认值。"""
    kb = KnowledgeBase(name="产品手册", description="v1")
    session.add(kb)
    session.flush()
    assert kb.id is not None
    assert kb.status == models.KBStatus.ENABLED

    doc = Document(
        kb_id=kb.id,
        name="手册.pdf",
        source_type=models.SourceType.UPLOAD,
        oss_key=f"kb/{kb.id}/doc/1/source.pdf",
        file_type="pdf",
        file_size=1024,
    )
    session.add(doc)
    session.flush()
    assert doc.status == models.DocumentStatus.UPLOADED
    assert doc.version == 1 and doc.enabled and not doc.edited
    assert doc.chunk_count == 0

    chunk = Chunk(document_id=doc.id, kb_id=kb.id, chunk_index=0, content="# 标题\n正文")
    session.add(chunk)
    session.flush()
    assert chunk.vectorized is False  # 对账扫描初始态
    assert chunk.created_at is not None  # server_default 生效

    app = App(name="客服机器人", kb_ids=[kb.id], api_key="ek-test-0001")
    session.add(app)
    session.flush()
    assert app.top_k == 5 and app.enabled and app.model_params == {}

    qa = QaRecord(app_id=app.id, user_key="u-001", question="怎么退货？", answer="…")
    session.add(qa)
    session.flush()
    assert qa.grounded and qa.feedback == models.Feedback.NONE

    t0 = datetime(2026, 11, 16, 12, 0, 0)
    root = TraceSpan(
        trace_id=qa.id,
        name="qa.root",
        span_type="llm",
        start_time=t0,
        end_time=t0 + timedelta(milliseconds=120),
        latency_ms=120,
    )
    session.add(root)
    session.flush()  # 先回填 root.id，子 span 才能引用
    child = TraceSpan(
        trace_id=qa.id,
        parent_span_id=root.id,
        name="gen_ai.chat",
        span_type=models.SpanType.LLM,
        start_time=t0 + timedelta(milliseconds=120),
        end_time=t0 + timedelta(milliseconds=218),
        latency_ms=98,
        gen_ai_usage_tokens_in=812,
        gen_ai_usage_tokens_out=233,
    )
    session.add(child)
    session.flush()
    assert child.trace_id == qa.id  # trace_id = qa_record.id 硬约定
    assert child.parent_span_id == root.id  # 树结构
    session.commit()  # 全链路可提交


def test_chunk_duplicate_index_allowed(session):
    """决策 3：替换窗口期同一 document_id 新旧 chunk 并存，无唯一约束。"""
    for _ in range(2):
        session.add(
            Chunk(document_id=42, kb_id=7, chunk_index=0, content="同序号并存")
        )
    session.commit()  # 不抛 IntegrityError 即通过


def test_admin_user_username_unique(session):
    session.add(AdminUser(username="admin", password_hash="x"))
    session.commit()
    session.add(AdminUser(username="admin", password_hash="y"))
    with pytest.raises(IntegrityError):
        session.commit()


def test_app_api_key_unique(session):
    session.add(App(name="a", kb_ids=[], api_key="ek-dup"))
    session.commit()
    session.add(App(name="b", kb_ids=[], api_key="ek-dup"))
    with pytest.raises(IntegrityError):
        session.commit()


def test_app_name_unique(session):
    """2026-11-16 二次修订：app.name 与 knowledge_base.name 对齐，唯一。"""
    session.add(App(name="客服机器人", kb_ids=[], api_key="ek-1"))
    session.commit()
    session.add(App(name="客服机器人", kb_ids=[], api_key="ek-2"))
    with pytest.raises(IntegrityError):
        session.commit()


def test_qa_record_snapshot_defaults(session):
    """2026-11-16 二次修订：落库时快照引用与模型参数，修反馈闭环断链。"""
    qa = QaRecord(app_id=1, user_key="u-001", question="q", answer="a")
    session.add(qa)
    session.flush()
    assert qa.citations == []  # 引用快照（含 doc_name/snippet/score 等）
    assert qa.model_snapshot == {}  # 模型参数快照（不含 api_key/base_url）


def test_tables_and_columns_have_comments():
    """2026-11-16 二次修订：表注释 + 全列注释落 MySQL DDL（SQLite 忽略，
    真实 DDL 以 SHOW CREATE TABLE 抽查为准）。"""
    for table in Base.metadata.sorted_tables:
        assert table.comment, f"表 {table.name} 缺表注释"
        for column in table.columns:
            assert column.comment, f"{table.name}.{column.name} 缺列注释"


def _mysql_ddl_lines():
    """对 mysql 方言离线编译各表 DDL（不出网），返回 {表名: {列名: DDL 行}}。

    方言编译器对安全的小写标识符不加反引号（引号是 MySQL 服务端行为），
    故按"行首列名 + 空格"匹配列行。
    """
    out = {}
    for table in Base.metadata.sorted_tables:
        ddl = str(CreateTable(table).compile(dialect=mysql.dialect()))
        lines = {}
        for line in ddl.splitlines():
            stripped = line.strip()
            for col in table.columns:
                if stripped.startswith(f"{col.name} "):
                    lines[col.name] = stripped
        out[table.name] = lines
    return out


def test_timestamp_columns_on_mysql():
    """2026-11-16 三次修订：时间戳列落 MySQL TIMESTAMP + 库端自动维护。

    created_at → timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP
    updated_at → 同上 + ON UPDATE CURRENT_TIMESTAMP（可变表才有）
    SQLite 方言经 with_variant 回落 DateTime，行为不变（其余测试守护）。
    """
    for table, lines in _mysql_ddl_lines().items():
        assert "created_at" in lines, f"{table} 缺 created_at"
        created = lines["created_at"].upper()
        assert "TIMESTAMP" in created, f"{table}.created_at 不是 TIMESTAMP：{created}"
        assert "DEFAULT CURRENT_TIMESTAMP" in created, f"{table}.created_at 缺库端默认：{created}"

        if "updated_at" not in lines:
            continue
        updated = lines["updated_at"].upper()
        assert "TIMESTAMP" in updated, f"{table}.updated_at 不是 TIMESTAMP：{updated}"
        assert "DEFAULT CURRENT_TIMESTAMP" in updated, f"{table}.updated_at 缺库端默认：{updated}"
        assert "ON UPDATE CURRENT_TIMESTAMP" in updated, f"{table}.updated_at 缺自动更新子句：{updated}"


def test_trace_span_time_columns_on_mysql():
    """2026-11-16 四次修订：trace_span 补 start_time/end_time，支撑时间轴视图。

    只有时长没有时刻，时间轴不知道横条画在哪、id 完成序在二期并行场景会排错。
    精度必须毫秒（fsp=3）：秒精度 TIMESTAMP 会把 45ms 噪声化成 0。
    """
    lines = _mysql_ddl_lines()["trace_span"]
    for col in ("start_time", "end_time"):
        assert col in lines, f"trace_span 缺 {col} 列"
        ddl = lines[col].upper()
        assert "TIMESTAMP(3)" in ddl, f"{col} 非毫秒精度 TIMESTAMP(3)：{lines[col]}"
        assert "NOT NULL" in ddl, f"{col} 应为 NOT NULL：{lines[col]}"
