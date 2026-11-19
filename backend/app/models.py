"""SQLAlchemy 表定义（一期全部 7 张表）。

蓝图见《设计文档 2026-11-14》§5.1，与设计文档的差异均为数据表讨论的
决策（冲突时以本文档与技术决策记录 §7 为准）：

2026-11-16 定稿（第一次）：
1. 新增 admin_user 表——设计文档 §7 要求"自建账密 + JWT"但 §5.1 未列表；
2. app 表新增 api_key（X-API-Key 鉴权落点，技术决策记录 §2.2）与 enabled；
3. chunk 表不加 UNIQUE(document_id, chunk_index)——§6.2 替换语义的窗口期内
   同一文档新旧 chunk 并存（新入库、成功后才按旧 ids 清理），唯一约束必炸；
4. 全部表不加物理外键，只用索引——删除/替换顺序（先 Milvus 后 MySQL 再
   存储层）由应用层保证，外键反而束缚批量清理；
5. qa_record / trace_span 随本期一次性建出（create_all 零成本），Plan 2 直接用。

2026-11-16 二次修订（review 后）：
6. 全表补表注释与列注释（MySQL COMMENT 落 DDL，SHOW CREATE TABLE 即文档；
   SQLite 忽略不影响测试）；
7. qa_record 新增 citations / model_snapshot 快照列——文档 md 编辑或替换重传
   会重新切块并按旧 ids 删除旧 chunk，不快照则历史问答引用 join 断链，
   §6.4 反馈闭环第一步即断；app.model_params 可编辑，模型快照固化当时取值
   （不含 api_key/base_url，避免密钥复制扩散）；
8. app.name 加唯一约束，与 knowledge_base.name 对齐。

2026-11-16 三次修订（review 后）：
9. created_at / updated_at 改 MySQL TIMESTAMP，库端自动维护——created_at
   DEFAULT CURRENT_TIMESTAMP；updated_at 另加 ON UPDATE CURRENT_TIMESTAMP
   （DDL 子句经 AutoUpdateTimestamp 自定义编译注入，仅 mysql 方言）。
   命名确认保持 created_at/updated_at（不改 create_at/update_at），列注释
   统一为 创建时间/修改时间；onupdate=func.now() 保留，维持 ORM 对象值
   同步；SQLite 测试库经 with_variant 回落 DateTime，行为不变。

2026-11-16 四次修订（review 后）：
10. trace_span 新增 start_time / end_time（TIMESTAMP(3) 毫秒精度，非空）——
    只有时长没有时刻时，时间轴视图无法摆位，id 完成序在二期 Agent 并行
    场景会排错；根 span 的 start_time 兼作「问题到达时刻」（qa_record.created_at
    是流结束写库时刻，答不了）。latency_ms 保留为物化冗余，聚合免
    TIMESTAMPDIFF。展示顺序 = 按 start_time 摆位 + parent_span_id 成树。
    纪律：时长用单调钟测、时刻用墙钟记；流结束后批量落库；观测写库
    失败 try/except 包死，绝不打断问答。锁定测试：
    test_trace_span_time_columns_on_mysql。

通用约定：
- 主键 BIGINT 自增；SQLite 测试库降级为 INTEGER（rowid 别名，否则不回填 id）；
- 时间戳 TIMESTAMP + 库端自动维护（见三次修订 9），可变表配 updated_at；
- 状态类字段用 SmallInteger（MySQL TINYINT）+ 本模块常量，不存字符串；
- MySQL JSON 字段用通用 JSON 类型，SQLite 测试库自动降级为 TEXT；
- 不加物理外键（决策 4），关联完整性由 services 层保证。
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.mysql import TIMESTAMP as MySQLTIMESTAMP
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

# BIGINT 主键在 SQLite 下必须渲染为 INTEGER 才能成为 rowid 别名并自动回填 id
ID_PK = BigInteger().with_variant(Integer(), "sqlite")


# ── 时间戳列（2026-11-16 三次修订：MySQL TIMESTAMP + 库端自动维护）────


class AutoUpdateTimestamp(MySQLTIMESTAMP):
    """MySQL TIMESTAMP，编译时追加 ON UPDATE CURRENT_TIMESTAMP 子句。

    仅注册 mysql 方言；SQLite 经 with_variant 回落 DateTime，测试库行为不变。
    """


@compiles(AutoUpdateTimestamp, "mysql")
def _render_auto_update_timestamp(element, compiler, **kw):
    return "TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"


# 类型对象可跨表共享：DEFAULT 子句由列级 server_default 提供（两种方言均合法）
CREATED_AT = DateTime().with_variant(MySQLTIMESTAMP(), "mysql")
UPDATED_AT = DateTime().with_variant(AutoUpdateTimestamp(), "mysql")
TIMESTAMP_MS = DateTime().with_variant(MySQLTIMESTAMP(fsp=3), "mysql")  # 毫秒精度时刻（span 起止）


# ── 状态常量（状态机与技术决策记录对齐）──────────────────────────


class KBStatus:
    ENABLED = 1
    DISABLED = 0  # 停用 = 整库不参与检索


class SourceType:
    UPLOAD = 1  # 上传文件
    WEBPAGE = 2  # 网页链接


class DocumentStatus:
    """文档状态机（设计文档 §6.1）：1→2→3→4→5→6，任一环节失败→7。"""

    UPLOADED = 1
    PARSING = 2
    EXTRACTED = 3  # content.md 已生成
    CHUNKED = 4
    VECTORIZING = 5
    COMPLETED = 6
    FAILED = 7  # status_reason 记因，可重试


class Feedback:
    NONE = 0
    GOOD = 1
    BAD = -1


class RetrievalMode:
    """检索模式（二期混合检索）：dense 纯向量 / hybrid 向量+BM25 RRF 融合。"""

    DENSE = "dense"
    HYBRID = "hybrid"


class SpanType:
    """span_type 枚举；tool / agent_step 为二期编排引擎预留（设计文档 §4）。

    parse / chunking / vector_insert 为二期 Task 29「解析管线纳入 Trace 观测」新增，
    对齐 OpenTelemetry GenAI 语义惯例之外的自定义入库链路类型。
    """

    EMBEDDING = "embedding"
    RETRIEVAL = "retrieval"
    DB = "db"
    LLM = "llm"
    TOOL = "tool"
    AGENT_STEP = "agent_step"
    # 二期 Task 29：解析管线各阶段
    PARSE = "parse"
    CHUNKING = "chunking"
    VECTOR_INSERT = "vector_insert"


# ── 管理域 ──────────────────────────────────────────────────────


class AdminUser(Base):
    """管理后台账号（Task 14 鉴权：pbkdf2 哈希 + JWT，实现见 core/security.py 与 api/auth.py）。"""

    __tablename__ = "admin_user"
    __table_args__ = {"comment": "管理后台账号（自建账密 + JWT 鉴权；首账号用 scripts/seed_admin.py 创建）"}

    id: Mapped[int] = mapped_column(ID_PK, primary_key=True, comment="主键，自增")
    username: Mapped[str] = mapped_column(String(64), unique=True, comment="登录名，唯一")
    password_hash: Mapped[str] = mapped_column(
        String(256), comment="密码哈希（pbkdf2 算法格式串，Task 14 定）"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, comment="False = 禁止登录")
    created_at: Mapped[datetime] = mapped_column(
        CREATED_AT, server_default=text("CURRENT_TIMESTAMP"), comment="创建时间"
    )
    updated_at: Mapped[datetime] = mapped_column(
        UPDATED_AT, server_default=text("CURRENT_TIMESTAMP"), onupdate=func.now(), comment="修改时间"
    )


# ── 知识域 ──────────────────────────────────────────────────────


class KnowledgeBase(Base):
    """知识库。"""

    __tablename__ = "knowledge_base"
    __table_args__ = {"comment": "知识库（status=0 停用 = 整库不参与检索；仅空库可删）"}

    id: Mapped[int] = mapped_column(ID_PK, primary_key=True, comment="主键，自增")
    name: Mapped[str] = mapped_column(String(128), unique=True, comment="库名，唯一")
    description: Mapped[str] = mapped_column(String(512), default="", comment="描述")
    status: Mapped[int] = mapped_column(
        SmallInteger, default=KBStatus.ENABLED, comment="1 启用 / 0 停用（停用 = 整库不参与检索）"
    )
    created_at: Mapped[datetime] = mapped_column(
        CREATED_AT, server_default=text("CURRENT_TIMESTAMP"), comment="创建时间"
    )
    updated_at: Mapped[datetime] = mapped_column(
        UPDATED_AT, server_default=text("CURRENT_TIMESTAMP"), onupdate=func.now(), comment="修改时间"
    )


class Document(Base):
    """文档，状态机驱动（设计文档 §6.1）。"""

    __tablename__ = "document"
    __table_args__ = (
        # 知识库详情页按库筛文档；worker 轮询 status∈(1, 3-编辑续跑, 7-重试) 领任务
        Index("ix_document_kb_status", "kb_id", "status"),
        Index("ix_document_status", "status"),
        {"comment": "文档（状态机驱动：1 已上传→…→6 已完成；7 失败可重试）"},
    )

    id: Mapped[int] = mapped_column(ID_PK, primary_key=True, comment="主键，自增")
    kb_id: Mapped[int] = mapped_column(
        BigInteger, comment="所属知识库 id（无物理外键，索引 ix_document_kb_status）"
    )
    name: Mapped[str] = mapped_column(String(256), comment="文档显示名")
    source_type: Mapped[int] = mapped_column(
        SmallInteger, default=SourceType.UPLOAD, comment="来源：1 上传文件 / 2 网页链接"
    )
    oss_key: Mapped[str] = mapped_column(
        String(512), default="", comment="原始文件/网页 html 快照对象路径 kb/{kb_id}/doc/{doc_id}/source.{ext}"
    )
    source_url: Mapped[Optional[str]] = mapped_column(
        String(1024), comment="网页来源 URL（source_type=2 时有值）"
    )
    file_type: Mapped[str] = mapped_column(String(16), default="", comment="文件类型：docx/pdf/xlsx/html")
    file_size: Mapped[int] = mapped_column(BigInteger, default=0, comment="原始文件字节数")
    status: Mapped[int] = mapped_column(
        SmallInteger,
        default=DocumentStatus.UPLOADED,
        comment="状态机：1 已上传→2 解析中→3 已提取→4 已切块→5 向量化中→6 已完成；7 失败",
    )
    status_reason: Mapped[Optional[str]] = mapped_column(String(512), comment="失败原因/重试依据")
    version: Mapped[int] = mapped_column(Integer, default=1, comment="替换重传 +1")
    enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, comment="False = 停用不参与检索（Milvus enabled 标志同步翻转）"
    )
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, comment="切块数冗余计数，列表页免 join")
    edited: Mapped[bool] = mapped_column(Boolean, default=False, comment="content.md 是否被人工编辑过")
    uploaded_by: Mapped[str] = mapped_column(String(64), default="", comment="上传人（管理后台账号名）")
    created_at: Mapped[datetime] = mapped_column(
        CREATED_AT, server_default=text("CURRENT_TIMESTAMP"), comment="创建时间"
    )
    updated_at: Mapped[datetime] = mapped_column(
        UPDATED_AT, server_default=text("CURRENT_TIMESTAMP"), onupdate=func.now(), comment="修改时间"
    )


class Chunk(Base):
    """内容切块，MySQL 与 Milvus 双存：id 兼作 Milvus 主键（rag_chunk collection）。

    无 UNIQUE(document_id, chunk_index)（决策 3）：§6.2 替换窗口期新旧并存。
    行不可变（重建 = 删旧插新），只有 created_at。
    """

    __tablename__ = "chunk"
    __table_args__ = (
        Index("ix_chunk_document", "document_id"),
        Index("ix_chunk_kb", "kb_id"),
        {"comment": "文档切块（MySQL 与 Milvus 双存；id 兼作 Milvus 主键；行不可变）"},
    )

    id: Mapped[int] = mapped_column(ID_PK, primary_key=True, comment="主键，兼作 Milvus rag_chunk 主键")
    document_id: Mapped[int] = mapped_column(BigInteger, comment="所属文档 id（无物理外键，索引 ix_chunk_document）")
    kb_id: Mapped[int] = mapped_column(
        BigInteger, comment="所属知识库 id（检索过滤冗余，免回表 document）"
    )
    chunk_index: Mapped[int] = mapped_column(Integer, comment="文档内序号（替换窗口期可与旧 chunk 同序号并存）")
    page_number: Mapped[Optional[int]] = mapped_column(
        Integer, comment="PDF 页码；md 编辑后可能失准置空；docx/xlsx/网页为 NULL"
    )
    content: Mapped[str] = mapped_column(Text, comment="切块正文（首行含所属标题行）")
    token_count: Mapped[int] = mapped_column(Integer, default=0, comment="token 数")
    vectorized: Mapped[bool] = mapped_column(Boolean, default=False, comment="True = 向量已在 Milvus（对账漂移扫描依据）")
    created_at: Mapped[datetime] = mapped_column(
        CREATED_AT, server_default=text("CURRENT_TIMESTAMP"), comment="创建时间"
    )


# ── 应用与观测域 ─────────────────────────────────────────────────


class App(Base):
    """产品侧机器人/场景：挂载知识库 + 问答参数 + 运行时模型配置。"""

    __tablename__ = "app"
    __table_args__ = {"comment": "应用/机器人（问答入口：挂载知识库 + 检索参数 + 模型配置，X-API-Key 鉴权）"}

    id: Mapped[int] = mapped_column(ID_PK, primary_key=True, comment="主键，自增")
    name: Mapped[str] = mapped_column(String(128), unique=True, comment="应用名，唯一")
    kb_ids: Mapped[list] = mapped_column(
        JSON, default=list, comment="挂载的知识库 id 列表（JSON，设计文档 §4 决策：不建关联表）"
    )
    api_key: Mapped[str] = mapped_column(
        String(64), unique=True, comment="X-API-Key 鉴权值，创建时生成、可重置"
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, comment="False = 一键停用问答入口")
    top_k: Mapped[int] = mapped_column(Integer, default=5, comment="检索返回条数")
    retrieval_mode: Mapped[str] = mapped_column(
        String(16), default=RetrievalMode.DENSE, comment="检索模式：dense 纯向量 / hybrid 向量+BM25 RRF 融合"
    )
    score_threshold: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 4), comment="相似度阈值（COSINE），NULL = 不过滤"
    )
    prompt_template: Mapped[Optional[str]] = mapped_column(Text, comment="自定义 Prompt 模板；NULL = 系统默认模板")
    model_params: Mapped[dict] = mapped_column(
        JSON, default=dict, comment="运行时模型配置 base_url/api_key/model 等（明文存储；admin API 读取时须脱敏）"
    )
    created_at: Mapped[datetime] = mapped_column(
        CREATED_AT, server_default=text("CURRENT_TIMESTAMP"), comment="创建时间"
    )
    updated_at: Mapped[datetime] = mapped_column(
        UPDATED_AT, server_default=text("CURRENT_TIMESTAMP"), onupdate=func.now(), comment="修改时间"
    )


class QaRecord(Base):
    """问答记录，兼作一条 Trace 的主表：trace_span.trace_id = 本表 id。

    追加不可变（反馈字段除外），只有 created_at。
    """

    __tablename__ = "qa_record"
    __table_args__ = (
        Index("ix_qa_record_app_created", "app_id", "created_at"),
        {"comment": "问答记录（兼作 Trace 主表：trace_span.trace_id = 本表 id；追加不可变，反馈字段除外）"},
    )

    id: Mapped[int] = mapped_column(ID_PK, primary_key=True, comment="主键，兼作 Trace id")
    app_id: Mapped[int] = mapped_column(BigInteger, comment="所属应用 id（无物理外键，索引 ix_qa_record_app_created）")
    user_key: Mapped[str] = mapped_column(String(128), comment="调用方透传的最终用户标识")
    session_id: Mapped[Optional[str]] = mapped_column(
        String(64), comment="多轮会话 id；一期单轮恒 NULL，二期启用（届时补索引）"
    )
    question: Mapped[str] = mapped_column(Text, comment="用户问题")
    answer: Mapped[str] = mapped_column(Text, comment="生成回答全文")
    grounded: Mapped[bool] = mapped_column(
        Boolean, default=True, comment="False = 零命中自由发挥（前端提示未基于知识库）"
    )
    chunk_ids: Mapped[list] = mapped_column(JSON, default=list, comment="命中 chunk id 列表（聚合分析用）")
    doc_ids: Mapped[list] = mapped_column(JSON, default=list, comment="命中文档 id 列表")
    scores: Mapped[list] = mapped_column(JSON, default=list, comment="与 chunk_ids 对位的相似度分数")
    citations: Mapped[list] = mapped_column(
        JSON,
        default=list,
        comment="引用快照：落库时下发的 citations 原样保存（doc_name/doc_id/chunk_id/page_number/snippet/score/source_url），"
        "防文档重切后旧 chunk 删除导致历史引用断链",
    )
    model_snapshot: Mapped[dict] = mapped_column(
        JSON,
        default=dict,
        comment="模型参数快照 {model, temperature…}（不含 api_key/base_url）；固化回答当时的取值",
    )
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, comment="端到端耗时（毫秒）")
    total_cost: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 6), comment="本次问答总花费（LLM+embedding）")
    feedback: Mapped[int] = mapped_column(
        SmallInteger, default=Feedback.NONE, comment="用户反馈：0 未反馈 / 1 满意 / -1 不满意"
    )
    created_at: Mapped[datetime] = mapped_column(
        CREATED_AT, server_default=text("CURRENT_TIMESTAMP"), comment="创建时间"
    )


class TraceSpan(Base):
    """链路步骤（Span 子表），字段命名对齐 OpenTelemetry GenAI 语义规范。

    parent_span_id 自引用构成树；二期编排引擎任意深度子树直接复用，
    界面按树渲染，零迁移。
    """

    __tablename__ = "trace_span"
    __table_args__ = (
        Index("ix_trace_span_trace", "trace_id"),
        {"comment": "链路步骤 Span（parent_span_id 自引用成树；命名对齐 OpenTelemetry GenAI 语义规范）"},
    )

    id: Mapped[int] = mapped_column(ID_PK, primary_key=True, comment="主键，自增")
    trace_id: Mapped[int] = mapped_column(BigInteger, comment="所属 Trace id（= qa_record.id）")
    parent_span_id: Mapped[Optional[int]] = mapped_column(BigInteger, comment="父 span id；NULL = 根，自引用成树")
    name: Mapped[str] = mapped_column(String(128), comment="span 名（如 gen_ai.embedding / milvus.search）")
    span_type: Mapped[str] = mapped_column(
        String(32), comment="类型：embedding/retrieval/db/llm/tool(预留)/agent_step(预留)"
    )
    input_summary: Mapped[Optional[str]] = mapped_column(Text, comment="输入摘要（截断存储，防大字段）")
    output_summary: Mapped[Optional[str]] = mapped_column(Text, comment="输出摘要（截断存储，防大字段）")
    start_time: Mapped[datetime] = mapped_column(TIMESTAMP_MS, comment="开始时刻（毫秒精度；时间轴零点 = 根 span 的本字段）")
    end_time: Mapped[datetime] = mapped_column(TIMESTAMP_MS, comment="结束时刻（毫秒精度）")
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, comment="本步耗时（毫秒，物化冗余，聚合免 TIMESTAMPDIFF）")
    gen_ai_usage_tokens_in: Mapped[Optional[int]] = mapped_column(Integer, comment="输入 token 数（GenAI 语义规范）")
    gen_ai_usage_tokens_out: Mapped[Optional[int]] = mapped_column(Integer, comment="输出 token 数（GenAI 语义规范）")
    cost: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 6), comment="本步花费")
    extra: Mapped[Optional[dict]] = mapped_column(JSON, comment="各 span_type 私有扩展字段")
    created_at: Mapped[datetime] = mapped_column(
        CREATED_AT, server_default=text("CURRENT_TIMESTAMP"), comment="创建时间"
    )
