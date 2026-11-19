"""Pydantic 请求/响应模型（Plan 1 Task 3 起；admin/open 两侧共用本模块）。"""
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


class KBCreate(BaseModel):
    """POST /kbs 请求体。"""

    name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=512)


class KBPatch(BaseModel):
    """PATCH /kbs/{id} 请求体：字段可选，未给的（None）不改。"""

    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=512)
    status: Literal[0, 1] | None = None  # 域对齐 models.KBStatus：越域 422，不静默落库


class KBOut(BaseModel):
    """知识库响应体（对齐 models.KnowledgeBase 列）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
    status: int
    created_at: datetime


# ── 鉴权（Task 14）───────────────────────────────────────────────


class LoginRequest(BaseModel):
    """POST /auth/login 请求体。"""

    username: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    password: Annotated[str, StringConstraints(min_length=1, max_length=128)]


class TokenOut(BaseModel):
    """POST /auth/login 响应体（单 access token，前端 localStorage + Authorization 头）。"""

    access_token: str
    token_type: str = "bearer"


class AdminUserOut(BaseModel):
    """GET /auth/me 响应体（密码哈希等敏感列绝不外发）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    is_active: bool
    created_at: datetime


class PasswordChangeRequest(BaseModel):
    """PUT /auth/password 请求体（user-center 改密码）。"""

    old_password: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    new_password: Annotated[str, StringConstraints(min_length=8, max_length=64)]


# ── 文档（Task 11）───────────────────────────────────────────────


class DocumentOut(BaseModel):
    """文档响应体（对齐 models.Document 列；oss_key 是存储内路径，属管线内部细节不外发）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    kb_id: int
    name: str
    source_type: int
    source_url: str | None = None
    file_type: str
    file_size: int
    status: int
    status_reason: str | None = None
    version: int
    enabled: bool
    chunk_count: int
    edited: bool
    uploaded_by: str
    created_at: datetime
    updated_at: datetime


class WebDocCreate(BaseModel):
    """POST /kbs/{kb_id}/documents/web 请求体：批量网页 ≤50 条/请求（Global Constraints）。"""

    urls: list[Annotated[str, StringConstraints(max_length=1024)]] = Field(
        min_length=1, max_length=50
    )


class DocumentEnabledPatch(BaseModel):
    """PATCH /documents/{id}/enabled 请求体。"""

    enabled: bool


class DocumentPageOut(BaseModel):
    """GET /kbs/{kb_id}/documents 分页响应体。"""

    total: int
    page: int
    size: int
    items: list[DocumentOut]


class ContentUpdate(BaseModel):
    """PUT /documents/{id}/content 请求体（md 编辑器保存）。"""

    content: Annotated[str, StringConstraints(min_length=1, max_length=1_000_000)]


class ContentOut(BaseModel):
    """GET /documents/{id}/content 响应体。"""

    document_id: int
    content: str


# ── 切块与对账（Task 13）────────────────────────────────────────


class ChunkOut(BaseModel):
    """GET /documents/{id}/chunks 单条切块响应体（对齐 models.Chunk 列）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    chunk_index: int
    page_number: int | None = None
    content: str
    token_count: int
    vectorized: bool


class ChunkPageOut(BaseModel):
    """GET /documents/{id}/chunks 分页响应体。"""

    total: int
    page: int
    size: int
    items: list[ChunkOut]


class ReconciliationItemOut(BaseModel):
    """GET /admin/reconciliation 单个异常文档。"""

    doc_id: int
    issue: str


# ── 应用管理（Task 18）─────────────────────────────────────────


class AppCreate(BaseModel):
    """POST /apps 请求体：api_key 服务端生成，创建时唯一一次明文返回。"""

    name: str = Field(min_length=1, max_length=128)
    kb_ids: list[int] = Field(default_factory=list)
    top_k: int = Field(default=5, ge=1, le=100)
    retrieval_mode: str = Field(default="dense", pattern="^(dense|hybrid)$")
    score_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    prompt_template: str | None = Field(default=None, max_length=10_000)
    model_params: dict = Field(default_factory=dict)


class AppPatch(BaseModel):
    """PATCH /apps/{id} 请求体：字段可选，未给的（None）不改。"""

    name: str | None = Field(default=None, min_length=1, max_length=128)
    kb_ids: list[int] | None = None
    top_k: int | None = Field(default=None, ge=1, le=100)
    retrieval_mode: str | None = Field(default=None, pattern="^(dense|hybrid)$")
    score_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    prompt_template: str | None = Field(default=None, max_length=10_000)
    model_params: dict | None = None
    enabled: bool | None = None


class AppOut(BaseModel):
    """应用响应体（对齐 models.App 列）；api_key 与 model_params.api_key 均脱敏。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    kb_ids: list[int]
    api_key: str
    enabled: bool
    top_k: int
    retrieval_mode: str = "dense"
    score_threshold: float | None = None
    prompt_template: str | None = None
    model_params: dict
    created_at: datetime
    updated_at: datetime


class AppCreateOut(BaseModel):
    """POST /apps 响应体：创建时 api_key 唯一一次明文返回。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    kb_ids: list[int]
    api_key: str  # 明文（仅创建时）
    enabled: bool
    top_k: int
    retrieval_mode: str = "dense"
    score_threshold: float | None = None
    prompt_template: str | None = None
    model_params: dict
    created_at: datetime
    updated_at: datetime


class AppKeyOut(BaseModel):
    """POST /apps/{id}/reset-key 响应体：重置后的新明文 api_key。"""

    api_key: str


# ── 问答（Task 21）─────────────────────────────────────────────


class ChatRequest(BaseModel):
    """POST /apps/{app_id}/chat 请求体（open 侧，X-API-Key 鉴权）。"""

    question: str = Field(min_length=1, max_length=10_000)
    user_key: str = Field(default="", max_length=128)


class FeedbackRequest(BaseModel):
    """POST /apps/{app_id}/feedback 请求体。"""

    record_id: int
    feedback: int  # 0 未反馈 / 1 满意 / -1 不满意（对齐 models.Feedback）


# ── 问答记录与 Trace 查看（Task 22）────────────────────────────


class QaRecordOut(BaseModel):
    """问答记录响应体（对齐 models.QaRecord 列）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    app_id: int
    user_key: str
    session_id: str | None = None
    question: str
    answer: str
    grounded: bool
    chunk_ids: list[int]
    doc_ids: list[int]
    scores: list[float]
    citations: list[dict]
    model_snapshot: dict
    latency_ms: int
    total_cost: float | None = None
    feedback: int
    created_at: datetime


class QaRecordPageOut(BaseModel):
    """GET /records 分页响应体。"""

    total: int
    page: int
    size: int
    items: list[QaRecordOut]


class TraceSpanOut(BaseModel):
    """span 响应体（对齐 models.TraceSpan 列）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    trace_id: int
    parent_span_id: int | None = None
    name: str
    span_type: str
    input_summary: str | None = None
    output_summary: str | None = None
    start_time: datetime
    end_time: datetime
    latency_ms: int
    gen_ai_usage_tokens_in: int | None = None
    gen_ai_usage_tokens_out: int | None = None
    cost: float | None = None
    extra: dict | None = None


class TraceSpanNode(BaseModel):
    """span 树节点：字段 + children（parent_span_id 成树）。"""

    id: int
    name: str
    span_type: str
    parent_span_id: int | None = None
    input_summary: str | None = None
    output_summary: str | None = None
    start_time: datetime
    end_time: datetime
    latency_ms: int
    gen_ai_usage_tokens_in: int | None = None
    gen_ai_usage_tokens_out: int | None = None
    cost: float | None = None
    extra: dict | None = None
    children: list["TraceSpanNode"] = []


class TraceTreeOut(BaseModel):
    """GET /traces/{trace_id} 响应体：根 span 列表（成树）。

    trace_id 语义二合一（二期 Task 29 起）：
    - 正整数 = 问答链路（qa_record.id）
    - 负整数 = 入库链路（-(doc_id)，管线 parse/chunking/embedding/vector_insert span）
    source 标识来源，pipeline 时附 doc 信息供查看器展示。
    """

    trace_id: int
    source: str  # "qa" | "pipeline"
    spans: list[TraceSpanNode]
    doc: "DocumentOut | None" = None


class PipelineTraceItem(BaseModel):
    """入库链路 Trace 列表项（GET /traces/pipeline）。"""

    trace_id: int  # 负数 = -(doc_id)
    doc_id: int
    doc_name: str | None = None
    kb_id: int | None = None
    doc_status: int | None = None
    span_count: int
    total_latency_ms: int
    last_start_time: datetime | None = None


class PipelineTracePageOut(BaseModel):
    """入库链路 Trace 分页响应体。"""

    total: int
    page: int
    size: int
    items: list[PipelineTraceItem]


class SpanAggregateItem(BaseModel):
    """单 span_type 的聚合指标。"""

    span_type: str
    count: int
    p95_latency_ms: int | None = None
    avg_tokens_in: float | None = None
    avg_tokens_out: float | None = None
    avg_cost: float | None = None


class TraceAggregateOut(BaseModel):
    """GET /traces/aggregate 响应体：最慢 Top N + 各 span_type P95。"""

    slowest: list[TraceSpanOut]
    by_type: list[SpanAggregateItem]


# ── 检索评测（二期 Task 28，admin 可视化页）──────────────────────


class AblationResultItem(BaseModel):
    """单路检索器的消融指标。"""

    key: str  # "dense" | "sparse" | "hybrid"
    label: str  # 中文名
    recall_at_k: float
    mrr: float
    hit_at_k: float


class AblationResultOut(BaseModel):
    """GET /evals/ablation 响应体：三路消融指标 + 实验元信息。"""

    generated_at: str
    top_k: int
    n_items: int
    n_chunks: int
    oversample: int
    rrf_k: int
    eval_kb: str
    seed: int
    results: list[AblationResultItem]


# ── 平台概况（dashboard 运营驾驶舱）──────────────────────────────


class DashboardTrendPoint(BaseModel):
    """单日问答趋势点。"""

    date: str  # YYYY-MM-DD
    count: int


class DashboardDocStatusItem(BaseModel):
    """文档状态分布项（status → 数量）。"""

    status: int
    count: int


class DashboardRetrievalModeItem(BaseModel):
    """检索模式分布项（dense/hybrid → 应用数）。"""

    mode: str
    count: int


class DashboardRecentQa(BaseModel):
    """最近问答摘要（概况页列表用）。"""

    id: int
    app_id: int
    question: str
    grounded: bool
    latency_ms: int
    created_at: datetime


class DashboardOut(BaseModel):
    """GET /dashboard 响应体：概况页全部统计。"""

    kb_count: int
    doc_count: int
    chunk_count: int
    app_count: int
    qa_count: int
    total_cost: float
    failed_doc_count: int
    qa_trend: list[DashboardTrendPoint]
    doc_status: list[DashboardDocStatusItem]
    retrieval_modes: list[DashboardRetrievalModeItem]
    recent_qa: list[DashboardRecentQa]
