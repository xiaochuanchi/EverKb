# 一期·后端地基 实施计划（Plan 1/3）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 从零建起 RAG 知识库平台的后端地基：可插拔存储/模型抽象、各格式解析为 Markdown、md 感知切块、向量化入 Milvus、全状态机处理管线、管理 REST API（含 md 编辑重入库）与管理端鉴权。

**Architecture:** FastAPI 单体 + 进程内 worker 线程轮询任务表；存储与模型全部抽象为 Protocol（本地磁盘/OpenAI 兼容端点为默认实现）；chunk 内容来自 content.md 并双存 MySQL 与 Milvus（MySQL chunk.id 兼作 Milvus 主键）。测试用 SQLite + Fake 双件套（FakeVector/FakeEmbedder/LocalDiskStorage），真实组件各配一个手动验证脚本。

**Tech Stack:** Python 3.11 / FastAPI / SQLAlchemy 2.0 (sync, PyMySQL) / pymilvus / oss2 / httpx / python-docx / PyMuPDF / openpyxl / trafilatura / PyJWT / pytest

**Spec:** `/Users/jiajia/Desktop/rag知识库设计文档/2026-11-14-rag知识库管理平台-设计文档.md`（v2；本计划覆盖其 §10 路线图第 1 步。问答链路 + Trace 埋点见 Plan 2，前端见 Plan 3）

**仓库位置（默认，可改）：** `/Users/jiajia/Desktop/rag-kb`

## Global Constraints

- Python ≥ 3.11；依赖装在 venv，`requirements.txt` 固定
- embedding 维度 **1024**；预置模型 text-embedding-v4，走 DashScope 兼容端点 `https://dashscope.aliyuncs.com/compatible-mode/v1`；一律 OpenAI 兼容协议（`base_url + api_key + model`）
- 切块：目标 **600 字符**（≈500 token）、重叠 **60 字符**；PDF 页标记格式 `<!-- page:N -->`
- 对象路径：`kb/{kb_id}/doc/{doc_id}/source.{ext}` 与 `kb/{kb_id}/doc/{doc_id}/content.md`
- Milvus：collection `rag_chunk`；HNSW(M=16, efConstruction=200) COSINE；`kb_id` 为 partition key；`chunk_text VARCHAR(16384)`；字段 id/vector/chunk_text/page_number/doc_id/kb_id/enabled
- 上传 ≤ 200MB；扩展名白名单 `docx/pdf/xlsx`；网页批量添加 ≤ 50 条/请求
- 文档状态枚举固定：1 已上传 / 2 解析中 / 3 已提取 / 4 已切块 / 5 向量化中 / 6 已完成 / 7 失败（常量名 `STATUS_UPLOADED..STATUS_FAILED`）
- 文档状态机硬约束：重试未完成文档先清残留 chunk；替换/md 编辑（已有完成版本）成功后才按旧 ids 精准清旧
- 测试不发起真实网络/云调用（用 Fake）；Milvus/OSS/embedding 真实验证走 `scripts/verify_*.py` 手动执行
- 代码风格：英文标识符 + 中文注释；提交信息用 Conventional Commits，结尾加 `Co-Authored-By: Claude Code <noreply@anthropic.com>`
- 一期不引入 Alembic：建表用 `Base.metadata.create_all`（设计决策：单人起步，模型变更期用删库重建）

## Review Focus

1. **扫描件 PDF（无文本层）**：必须失败（status=7，reason 含"扫描件"），绝不允许产出 0 chunk 却"已完成"——Task 10 测试 `test_scanned_pdf_fails`
2. **替换/md 编辑后旧向量残留**：旧 chunk ids 必须从 Milvus 精准清除，不允许同 doc_id 新旧永久并存——Task 10 测试 `test_replace_clears_old_chunk_ids`
3. **删除文档后 Milvus 残留可命中**：删除顺序必须 Milvus 先行——Task 11 测试 `test_delete_document_removes_vectors_first`
4. **半途崩溃的状态卡死**：非 6 状态的文档重试时先清残留（MySQL chunk + Milvus by doc_id）——Task 10 测试 `test_retry_cleans_leftover_chunks`
5. **切块破坏结构**：表格行不跨 chunk 拆断、页标记剥离干净、chunk_index 连续——Task 7 测试 `test_table_rows_not_split` / `test_page_markers_extracted`
6. **超大单段**：句级硬切保证单 chunk ≤ target×2 且带重叠——Task 7 测试 `test_long_paragraph_hard_split`

---

### Task 1: 仓库骨架与基础设施

**Files:**
- Create: `docker-compose.yml`, `.env.example`, `requirements.txt`, `.gitignore`
- Create: `backend/app/__init__.py`, `backend/app/main.py`, `backend/app/core/config.py`, `backend/app/core/db.py`
- Test: `backend/tests/test_health.py`, `backend/tests/conftest.py`

**Interfaces:**
- Produces: `create_app(settings: Settings | None = None, *, storage=None, embedder=None, vector=None) -> FastAPI`（依赖注入缝，后续任务全靠它换 Fake）；`get_settings() -> Settings`（lru_cache）；`Base`, `SessionLocal`, `get_db()`, `init_db()`

- [ ] **Step 1: 初始化仓库**

```bash
mkdir -p /Users/jiajia/Desktop/rag-kb && cd /Users/jiajia/Desktop/rag-kb && git init
mkdir -p backend/app/core backend/app/api backend/app/parsers backend/app/services backend/tests scripts frontend
python3.11 -m venv .venv && source .venv/bin/activate
```

- [ ] **Step 2: 写 `requirements.txt` 并安装**

```
fastapi>=0.115,<1
uvicorn[standard]>=0.30
sqlalchemy>=2.0,<3
pymysql>=1.1
cryptography>=42          # pymysql 认证依赖
pydantic>=2.7
pydantic-settings>=2.3
python-multipart>=0.0.9   # 文件上传
httpx>=0.27
pyjwt>=2.8
oss2>=2.18
pymilvus>=2.5
python-docx>=1.1
pymupdf>=1.24
openpyxl>=3.1
trafilatura>=1.8
pytest>=8
```

`pip install -r requirements.txt`

- [ ] **Step 3: 写 `docker-compose.yml`**（mysql:8 + etcd + minio + milvus standalone `milvusdb/milvus:v2.5.x`，端口仅绑 127.0.0.1；mysql 挂卷；milvus 依赖 etcd/minio 健康检查）

- [ ] **Step 4: 写 `.env.example`**（全部 Settings 字段见 Task 1 Step 5，含三组预置注释：豆包 `https://ark.cn-beijing.volces.com/api/v3`、DashScope 兼容模式、Ollama `http://localhost:11434/v1`）

- [ ] **Step 5: 实现 `config.py`** —— `Settings(BaseSettings)` 字段：`mysql_url` `milvus_uri` `collection_name="rag_chunk"` `storage_backend="local"|"oss"` `storage_root="./data/storage"` `oss_endpoint/oss_access_key_id/oss_access_key_secret/oss_bucket` `embedding_base_url/embedding_api_key/embedding_model/embedding_dim=1024/embedding_batch_size=10` `jwt_secret` `jwt_expire_hours=24` `admin_username="admin"` `admin_password_hash` `chunk_target_chars=600` `chunk_overlap_chars=60` `upload_max_bytes=209715200` `web_doc_max_urls=50` `worker_enabled=True` `worker_interval_sec=5`

- [ ] **Step 6: 实现 `db.py` 与 `main.py`**（engine/SessionLocal/Base/get_db/init_db；`create_app` 注册 `/health` 返回 `{"status":"ok"}`；storage/embedder/vector 参数为 None 时按 settings 构造真实实现并挂到 `app.state`）

- [ ] **Step 7: 写失败测试** `backend/tests/test_health.py`

```python
def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
```

`conftest.py`：构造测试 Settings（`mysql_url="sqlite:///:memory:"`、`storage_backend="local"`、`storage_root=tmp_path`、`worker_enabled=False`、`jwt_secret="test"`、`admin_password_hash` 为 "test1234" 的哈希），`LocalDiskStorage` 注入，`vector`/`embedder` 先用占位 None（后续任务补 Fake）；fixture `client = TestClient(create_app(settings, storage=local_storage))`。

- [ ] **Step 8: 跑测试** `pytest backend/tests/test_health.py -v` → PASS
- [ ] **Step 9: Commit** `chore: project skeleton with fastapi app, config, db, compose`

### Task 2: 数据模型（3 表）

**Files:**
- Create: `backend/app/models.py`
- Test: `backend/tests/test_models.py`

**Interfaces:**
- Produces: 模型 `KnowledgeBase` `Document` `Chunk`；状态常量 `STATUS_UPLOADED=1, STATUS_PARSING=2, STATUS_EXTRACTED=3, STATUS_CHUNKED=4, STATUS_EMBEDDING=5, STATUS_READY=6, STATUS_FAILED=7`

- [ ] **Step 1: 写失败测试**：建 KB→Document→Chunk 回环；断言 `doc.status == STATUS_UPLOADED`、`doc.enabled is True`、`doc.edited is False`、`doc.version == 1`、`chunk.vectorized is False`、`kb.status == 1`
- [ ] **Step 2: 跑测试确认失败**（ModuleNotFoundError）
- [ ] **Step 3: 实现 models.py**：字段按设计文档 §5.1（本计划只建 knowledge_base/document/chunk 三表；app/qa_record/trace_span 属 Plan 2）。`init_db()` 调 `Base.metadata.create_all`
- [ ] **Step 4: 跑测试** → PASS
- [ ] **Step 5: Commit** `feat: core models kb document chunk`

### Task 3: 知识库 API

**Files:**
- Create: `backend/app/schemas.py`, `backend/app/api/kb.py`（main.py 注册路由前缀 `/api`）
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_kb_api.py`

**Interfaces:**
- Produces: `POST /api/kbs` 201 / `GET /api/kbs` / `PATCH /api/kbs/{id}` / `DELETE /api/kbs/{id}`（409 若库内有文档或名字重复）；schemas `KBCreate(name, description="")`、`KBOut(id, name, description, status, created_at)`

- [ ] **Step 1: 写失败测试**：创建 201 且返回 id；重名 409；PATCH 改 status=0；DELETE 空库 204、含文档库 409（先手动插一个 document）
- [ ] **Step 2: 跑测试确认失败**
- [ ] **Step 3: 实现**（同步 def 端点 + Depends(get_db)）
- [ ] **Step 4: 跑测试** → PASS
- [ ] **Step 5: Commit** `feat: knowledge base crud api`

### Task 4: 存储抽象（Local + OSS）

**Files:**
- Create: `backend/app/core/storage/__init__.py`（含 `create_storage(settings)`）, `base.py`, `local.py`, `oss.py`
- Create: `scripts/verify_oss.py`
- Test: `backend/tests/test_storage.py`

**Interfaces:**
- Produces: `StorageClient` Protocol：`put_bytes(key: str, data: bytes) -> None` / `get_bytes(key: str) -> bytes`（缺失抛 FileNotFoundError）/ `delete(key: str) -> None`（缺失静默）/ `presign(key: str, expires_sec: int = 3600) -> str`
- `LocalDiskStorage(root: str)`：`presign` 返回 `f"local://{key}"`（测试/本地用）
- `OssStorage(settings)`：oss2 Bucket 封装，presign 用 `bucket.sign_url("GET", key, expires_sec)`
- `create_storage(settings) -> StorageClient`：按 `storage_backend` 分派

- [ ] **Step 1: 写失败测试**：put→get 回环一致；get 不存在抛 FileNotFoundError；delete 后 get 抛；presign 前缀 `local://`
- [ ] **Step 2: 跑测试确认失败**
- [ ] **Step 3: 实现 base/local**；oss.py 同步实现 + `scripts/verify_oss.py`（put/get/presign/delete 四步打印结果）
- [ ] **Step 4: 跑测试** → PASS；有 OSS 凭据时手动跑 `python scripts/verify_oss.py` 核对
- [ ] **Step 5: Commit** `feat: pluggable storage local disk + aliyun oss`

### Task 5: 解析器框架 + docx → Markdown

**Files:**
- Create: `backend/app/parsers/__init__.py`, `base.py`, `registry.py`, `docx_parser.py`
- Test: `backend/tests/test_docx_parser.py`

**Interfaces:**
- Produces:
```python
@dataclass
class ParseResult:
    ok: bool
    markdown: str = ""
    reason: str | None = None      # ok=False 时的失败原因（中文，写 status_reason）

class Parser(Protocol):
    def parse(self, data: bytes, filename: str) -> ParseResult: ...

SUPPORTED_FILE_TYPES = {"docx", "pdf", "xlsx"}
def get_parser(file_type: str) -> Parser    # 未知类型抛 ValueError
```

- [ ] **Step 1: 写失败测试**：测试内用 python-docx 现场构建 docx（Heading 1 "产品介绍"、正文两段、List Bullet 一条、2×3 表格）→ `parse` 断言：`ok is True`；md 含 `# 产品介绍`；含 `- ` 列表项；表格转为管道表（含 `| ` 行且行数=3）；正文段落保留
- [ ] **Step 2: 跑测试确认失败**
- [ ] **Step 3: 实现**：docx 映射规则——style 名以 `Heading`/`标题` 开头取级别 N → `#`×N；`List` 开头 → `- ` 前缀；普通段落原样；表格逐行转 `| a | b |`（首行后插 `|---|---|`）；空段落跳过
- [ ] **Step 4: 跑测试** → PASS
- [ ] **Step 5: Commit** `feat: parser framework and docx to markdown`

### Task 6: pdf / xlsx / html 解析 + 网页抓取

**Files:**
- Create: `backend/app/parsers/pdf_parser.py`, `xlsx_parser.py`, `webpage.py`（含 fetch + html_to_markdown）, 更新 `registry.py`
- Test: `backend/tests/test_pdf_parser.py`, `test_xlsx_parser.py`, `test_webpage.py`

**Interfaces:**
- Produces: `PdfParser`（逐页文本，页间插 `\n\n<!-- page:N -->\n\n`，全文 < 20 字符 → `ok=False, reason="疑似扫描件：未提取到文本层，请上传文字版或等待 OCR 支持"`）；`XlsxParser`（每 sheet 表头+数据行转管道表，数据行 > 20 拆多张表；sheet 首块前插 `# 工作表: {name}`）；`html_to_markdown(html: bytes) -> str`（trafilatura `output_format="markdown"`，空结果抛 `ParseError`）；`fetch_and_extract(url: str, timeout: float = 30.0) -> tuple[bytes, str]`（httpx 拉取 UA `rag-kb/0.1`，返回 (html_bytes, md)；thin 不做单测）

- [ ] **Step 1: 写失败测试（pdf）**：fitz 现场造 2 页 PDF（各插文本）→ ok=True，md 含 `<!-- page:1 -->` 与 `<!-- page:2 -->` 及两页文字；造无文本 PDF → ok=False 且 reason 含 "扫描件"
- [ ] **Step 2: 写失败测试（xlsx）**：openpyxl 造 sheet（表头 3 列 + 25 行数据）→ 管道表拆为两张（20 行 + 5 行），含 `# 工作表: Sheet` 标题
- [ ] **Step 3: 写失败测试（html）**：内联一段含 `<article>` 正文与 `<nav>` 导航的 html → `html_to_markdown` 返回含正文关键词、不含导航文案；空 body html → 抛 ParseError
- [ ] **Step 4: 跑测试确认失败 → 实现 → 跑测试** → PASS（registry：`get_parser("pdf")`/`("xlsx")` 返回对应实例，`get_parser("doc")` 抛 ValueError）
- [ ] **Step 5: Commit** `feat: pdf xlsx html parsers with page markers`

### Task 7: Markdown 切块器

**Files:**
- Create: `backend/app/services/__init__.py`, `backend/app/services/chunking.py`
- Test: `backend/tests/test_chunking.py`

**Interfaces:**
- Produces:
```python
@dataclass
class ChunkDraft:
    content: str
    chunk_index: int            # 0 起连续
    page_number: int | None     # 来自最近一个 page 标记

def chunk_markdown(md: str, target: int = 600, overlap: int = 60) -> list[ChunkDraft]
def estimate_tokens(text: str) -> int      # len(text)，中文近似；预留换 tokenizer
```

算法（唯一允许的实现分歧点已在此钉死）：逐行扫描——`<!-- page:N -->` 更新当前页码并丢弃；`#`~`######` 标题行开新段；连续 `|` 开头行为表格块（原子）；空行丢弃。段内按句边界 `(?<=[。！？!?；;\n])` 切句打包：缓冲超 target 且非空则 flush 为 chunk（下一 chunk 以被 flush 内容末尾 overlap 字符开头）；单句超 target×2 硬切（步长 target，重叠 overlap）。chunk.content 首行为所属最近标题行（若正文首行不是该标题）；page_number 取段前最近标记。

- [ ] **Step 1: 写失败测试**
  - `test_headings_split`：`# A`+100字、`## B`+100字，target=600 → 2 chunks，第二个首行 `## B`
  - `test_page_markers_extracted`：`<!-- page:3 -->` 后的文本 → chunk.page_number==3 且正文无 `<!--`
  - `test_long_paragraph_hard_split`：1500 字无标题文本 → 3+ chunks，`chunk[1].content[:60] == chunk[0].content.rstrip()[-60:]`，均 ≤ 1200
  - `test_table_rows_not_split`：600+ 字符表格（每行 20 字×35 行）→ 所有 chunk 中以 `|` 开头的行拼起来行数 == 35，且每个 chunk 内表格行都完整
  - `test_overlap_carry`：三段各 300 字 target=600 → 1 chunk（不重叠）；两段各 400 字 → 2 chunks 且第二 chunk 以第一 chunk 末 60 字开头
  - `test_index_continuous`：任意输入 → `[c.chunk_index for c] == list(range(n))`
- [ ] **Step 2: 跑测试确认失败**
- [ ] **Step 3: 实现 chunk_markdown**
- [ ] **Step 4: 跑测试** → PASS
- [ ] **Step 5: Commit** `feat: markdown-aware chunker with page markers and atomic tables`

### Task 8: Embedding 客户端（OpenAI 兼容）

**Files:**
- Create: `backend/app/services/embedding/__init__.py`（`create_embedder(settings)`）, `base.py`, `openai_compatible.py`, `fakes.py`
- Create: `scripts/verify_embedding.py`
- Test: `backend/tests/test_embedding.py`

**Interfaces:**
- Produces: `Embedder` Protocol：`embed(texts: list[str]) -> list[list[float]]`（维度 = embedding_dim）；`OpenAIEmbedder(base_url, api_key, model, dim, batch_size=10, max_retries=3)`——POST `{base_url}/embeddings`，自动分批（≤batch_size），429/5xx 退避重试；`FakeEmbedder(dim=1024)`——确定性向量 `[float((len(text)*31+i) % 97) / 97 for i in range(dim)]`（相同文本恒等）

- [ ] **Step 1: 写失败测试**：FakeEmbedder 返回 dim 维、同文本两次调用结果相等；`OpenAIEmbedder` 用 `httpx.MockTransport` 模拟端点——12 条文本按 batch_size=10 恰好 2 次请求、每次请求体 ≤10 条、返回 12 个向量；MockTransport 先 500 后 200 → 重试成功
- [ ] **Step 2: 跑测试确认失败 → 实现 → 跑测试** → PASS
- [ ] **Step 3: 手动验证**（有凭据时）：`python scripts/verify_embedding.py`（DashScope 兼容模式 + text-embedding-v4 + dim=1024，打印 2 条文本的向量维度与相似度）
- [ ] **Step 4: Commit** `feat: openai-compatible embedder with batching and retry`

### Task 9: Milvus 向量客户端

**Files:**
- Create: `backend/app/services/vector/__init__.py`（`create_vector(settings)`）, `base.py`, `milvus.py`, `fakes.py`
- Create: `scripts/verify_milvus.py`
- Test: `backend/tests/test_vector_fakes.py`

**Interfaces:**
- Produces:
```python
@dataclass
class VectorRow:
    id: int; vector: list[float]; chunk_text: str; page_number: int | None
    doc_id: int; kb_id: int; enabled: bool

@dataclass
class SearchHit:
    chunk_id: int; doc_id: int; kb_id: int; score: float
    chunk_text: str; page_number: int | None

class VectorClient(Protocol):
    def ensure_collection(self) -> None                      # 幂等建 collection+索引
    def insert(self, rows: list[VectorRow]) -> None
    def search(self, query_vector: list[float], kb_ids: list[int],
               top_k: int = 5, threshold: float | None = None) -> list[SearchHit]
    def delete_by_doc(self, doc_id: int) -> None
    def delete_by_ids(self, ids: list[int]) -> None
    def set_doc_enabled(self, doc_id: int, enabled: bool) -> None   # query 取回含 vector 后 upsert 翻标志
    def count_by_doc(self, doc_id: int) -> int
```

- [ ] **Step 1: 写失败测试（FakeVector 语义）**：insert→search 命中且 kb 过滤生效（只查指定 kb_ids）、enabled=False 不命中、threshold 过滤；delete_by_doc / delete_by_ids / set_doc_enabled / count_by_doc 语义各一条断言
- [ ] **Step 2: 跑测试确认失败 → 实现 fakes → 跑测试** → PASS
- [ ] **Step 3: 实现 milvus.py**（pymilvus MilvusClient；ensure_collection 幂等；schema 按 Global Constraints；`set_doc_enabled` = query(output_fields 含 "vector") → 翻 enabled → upsert）
- [ ] **Step 4: 手动验证**：`docker compose up -d` 后 `python scripts/verify_milvus.py`（建表→插 3 条→search 断言命中→按 doc 删→count==0，打印 PASS）
- [ ] **Step 5: Commit** `feat: milvus vector client with fake for tests`

### Task 10: 处理管线（状态机 + 幂等 + 替换语义）

**Files:**
- Create: `backend/app/services/pipeline.py`
- Modify: `backend/app/models.py`（无结构变更，导出常量即可）
- Test: `backend/tests/test_pipeline.py`

**Interfaces:**
- Consumes: StorageClient / Parser / chunk_markdown / Embedder / VectorClient（均前述签名）
- Produces:
```python
def process_document(session: Session, doc_id: int, *, storage: StorageClient,
                     embedder: Embedder, vector: VectorClient, settings: Settings) -> None
def run_pending(session_factory, *, storage, embedder, vector, settings) -> int   # 处理所有 status==1，返回处理数
```

流程（顺序钉死）：载入 doc → status=2 → 取内容（文件 `get_bytes(oss_key)`；网页 `fetch_and_extract(source_url)` 后把 html 快照 put 到 oss_key）→ parser.parse → **未完成过的文档（status≠6 进入）先清残留 chunk 行与 `vector.delete_by_doc`** → md `put_bytes(content.md 路径)`，status=3 → `chunk_markdown`，插 chunk 行（vectorized=False），status=4 → `embedder.embed`（按 batch 分批）→ `vector.insert(rows, enabled=doc.enabled)`，chunk.vectorized=True，status=5 → **替换收尾：若进入时 doc.status==6（已有完成版本），先记录的 old_ids 执行 `vector.delete_by_ids(old_ids)` + 删旧行** → chunk_count、status=6 提交。任一步异常：status=7 + status_reason=异常摘要（截 500 字），提交后返回。

- [ ] **Step 1: 写失败测试**（conftest 注入 FakeVector/FakeEmbedder，并提供便于造文档的 helper：插 doc 行 + 预置 source 文件到 LocalStorage）
  - `test_happy_path_docx`：走完 → status==6，content.md 存在于 storage，所有 chunk.vectorized is True，FakeVector.count_by_doc==chunk 行数，row.enabled==doc.enabled
  - `test_scanned_pdf_fails`：无文本 PDF → status==7，reason 含"扫描件"，0 chunk
  - `test_retry_cleans_leftover_chunks`：预置 status==4 + 2 条残留 chunk 行 + FakeVector 已有 2 条 → 处理后 MySQL 中旧 id 不存在（全新 ids），FakeVector 中旧 id 被清
  - `test_replace_clears_old_chunk_ids`：已完成的 doc（2 chunks）→ 覆盖 source、version=2、status=1 → 处理后新 ids 入库、`fake.deleted_ids` 恰含旧 ids、status==6
  - `test_web_document`：monkeypatch `fetch_and_extract` 返回 (html, md) → oss_key 处有 html 快照、正常完成
- [ ] **Step 2: 跑测试确认失败**
- [ ] **Step 3: 实现 process_document / run_pending**（`run_pending` 循环取 status==1 逐个 process，单个失败不影响后续）
- [ ] **Step 4: 跑测试** → PASS
- [ ] **Step 5: Commit** `feat: ingestion pipeline with state machine and replace semantics`

### Task 11: 文档 API + Worker

**Files:**
- Create: `backend/app/api/documents.py`, `backend/app/workers.py`
- Modify: `backend/app/main.py`（startup：`init_db`、`vector.ensure_collection()`、`worker_enabled` 时起 `start_worker` 守护线程）
- Test: `backend/tests/test_documents_api.py`

**Interfaces:**
- Produces: `POST /api/kbs/{kb_id}/documents`（multipart file；201 DocumentOut；413 超 200MB；400 非白名单扩展名）；`POST /api/kbs/{kb_id}/documents/web` body `{"urls": [...]}`（≤50，201 返回列表）；`GET /api/kbs/{kb_id}/documents?status=&page=&size=`；`GET /api/documents/{id}`；`PUT /api/documents/{id}/file`（替换：覆盖 source、version+1、status=1）；`POST /api/documents/{id}/retry`（仅 status==7，否则 409；置回 1）；`PATCH /api/documents/{id}/enabled` body `{"enabled": bool}`（同步 `vector.set_doc_enabled`）；`DELETE /api/documents/{id}`（顺序：`vector.delete_by_doc` → 删 chunk 行 → 删 doc → storage.delete）；`workers.start_worker(session_factory, deps, interval)` 循环调 `run_pending`

- [ ] **Step 1: 写失败测试**
  - 上传合法 docx → 201、status==1、oss_key 有对象；超限 → 413；`.doc` → 400
  - web 批量 2 条 → 201 两行 source_type==2；51 条 → 422
  - retry：status==7 → 200 回 status==1；status==6 → 409
  - enabled PATCH → doc.enabled 翻转且 `fake.set_enabled_calls` 记录了 (doc_id, False)
  - delete：`fake.deleted_doc_ids` 含该 id、chunk 行清空、storage 无对象
  - 替换 PUT file → version==2、status==1、旧 content.md 未动（待管线收尾）
  - `run_pending` 直接调用处理队列并返回处理数
- [ ] **Step 2: 跑测试确认失败 → 实现 → 跑测试** → PASS
- [ ] **Step 3: Commit** `feat: document lifecycle api and background worker`

### Task 12: md 编辑 API（保存即重新入库）

**Files:**
- Create: `backend/app/api/content.py`
- Modify: `backend/app/services/pipeline.py`（抽取 `rebuild_from_markdown` 公共函数）
- Test: `backend/tests/test_content_api.py`

**Interfaces:**
- Consumes: 复用 Task 10 替换语义（抽取公共函数 `rebuild_from_markdown(session, doc, md, *, embedder, vector, settings) -> None`：记 old_ids → 清残留（未完成时）→ chunk→embed→insert→收尾清旧，status 走 4→5→6）
- Produces: `GET /api/documents/{id}/content`（storage 读 content.md，404 若无）；`PUT /api/documents/{id}/content` body `{"markdown": str}` → 覆盖 content.md、`edited=True`、重建向量；version 不变、source 不动

- [ ] **Step 1: 写失败测试**：已完成的 doc → PUT 新 md → 200；处理后 chunk 数与新 md 切块数一致、旧 chunk ids 已从 MySQL 与 FakeVector 消失、edited is True、version==1；GET 返回刚保存的 md；对 status==6 之外的文档 PUT → 409
- [ ] **Step 2: 跑测试确认失败**
- [ ] **Step 3: 实现**（pipeline 中抽 `rebuild_from_markdown` 供 Task 10 替换收尾与 Task 12 共用——替换= 重新解析后调它）
- [ ] **Step 4: 跑测试** → PASS
- [ ] **Step 5: Commit** `feat: markdown content edit api with re-ingestion`

### Task 13: chunk 浏览 API + 对账

**Files:**
- Create: `backend/app/api/chunks.py`, `backend/app/api/reconciliation.py`
- Test: `backend/tests/test_chunks_api.py`

**Interfaces:**
- Produces: `GET /api/documents/{id}/chunks?page=1&size=50`（按 chunk_index 升序，返回 `ChunkOut(id, chunk_index, page_number, content, token_count, vectorized)` 与总数）；`GET /api/admin/reconciliation`（返回异常文档列表：`status==6 且存在 vectorized=False chunk` 或 `mysql chunk 数 != vector.count_by_doc`，元素 `{doc_id, issue}`）

- [ ] **Step 1: 写失败测试**：造 3 chunks → 分页正确、顺序正确；把一条 chunk.vectorized 置 False → reconciliation 命中且 issue 含 "unvectorized"；FakeVector.delete 一条制造计数差 → 命中且 issue 含 "count_mismatch"
- [ ] **Step 2: 跑测试确认失败 → 实现 → 跑测试** → PASS
- [ ] **Step 3: Commit** `feat: chunk browsing and reconciliation endpoints`

### Task 14: 管理端鉴权

**Files:**
- Create: `backend/app/core/security.py`, `backend/app/api/auth.py`
- Modify: 全部 `/api` 管理路由挂 `Depends(require_admin)`
- Test: `backend/tests/test_auth.py`

**Interfaces:**
- Produces: `hash_password(pw) -> "salt$hex"`（pbkdf2_hmac-sha256, 120_000 轮）/ `verify_password(pw, hashed) -> bool`；`create_access_token(username, settings) -> str`（HS256, exp=jwt_expire_hours）/ `require_admin(credentials) -> str`；`POST /api/auth/login {"username","password"}` → `{"access_token": ...}`，失败 401

- [ ] **Step 1: 写失败测试**：无 token 访问 `/api/kbs` → 401；带伪造 token → 401；登录成功拿 token 后访问 → 200；错误密码 → 401；`verify_password` 正反例
- [ ] **Step 2: 跑测试确认失败 → 实现 → 跑测试** → PASS
- [ ] **Step 3: Commit** `feat: admin auth pbkdf2 + jwt`

### Task 15: 端到端冒烟（真实组件）

**Files:**
- Create: `scripts/smoke_e2e.py`

- [ ] **Step 1: 写脚本**：配置读 `.env` → 登录取 token → 建 kb → 生成一个 docx（python-docx 内存构建）上传 → 轮询 `GET /api/documents/{id}` 直到 status==6（超时 120s）→ 列 chunks 断言 >0 → 用 chunk 文本第一句调问答检索辅助接口?（无——直接用 MilvusClient 按 kb_id 过滤 search 断言命中该 doc 的 chunk）→ 打印 `PASS`
- [ ] **Step 2: 执行**：`docker compose up -d` → 起后端 `uvicorn app.main:app --reload` → `python scripts/smoke_e2e.py` → 输出 PASS
- [ ] **Step 3: Commit** `test: end-to-end smoke script for real stack`

---

## 完成标准（Plan 1 Definition of Done）

1. `pytest backend/tests -v` 全绿
2. `scripts/smoke_e2e.py` 对真实 MySQL+Milvus(+OSS 可选) 输出 PASS
3. curl 可完成：建库 → 上传 docx → 轮询到已完成 → 看 chunks → PUT 改 md → chunks 重建
4. Review Focus 6 条各有对应通过的测试
5. 后续入口就绪：Plan 2（问答 + Trace 埋点）直接消费 `VectorClient.search` / `Embedder` / `create_app` 注入缝
