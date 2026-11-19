# EverKB · 可观测的 RAG 知识库平台

> 一个为「长期运营」而设计的 RAG 知识库管理平台。
> 不只是把文档丢进去就能聊——而是让知识库**不会腐烂**、让回答**可以定位**、让链路**看得见**。

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi)](https://fastapi.tiangolo.com/)
[![Vue](https://img.shields.io/badge/Vue-3-4FC08D?logo=vuedotjs&logoColor=white)](https://vuejs.org/)
[![Milvus](https://img.shields.io/badge/Milvus-2.5-00A1EA)](https://milvus.io/)

---

## 为什么是 EverKB？

市面上的开源 RAG 平台（Dify、RAGFlow、MaxKB、FastGPT、AnythingLLM）都瞄准了**接入期**——传文档、建机器人、聊起来。它们做得很好，但你一旦用上三个月，就会撞上三个没人解决的问题：

| 问题 | 现有平台的答案 | EverKB 的答案 |
|---|---|---|
| **知识库会腐烂**：文档更新了、删了、停用了，但旧向量还在被检索命中 | 「你手动删掉重新传」 | **文档生命周期状态机** + 替换重传 + 启停 + 失败重试，自动重新切块/向量化 |
| **回答变差无法定位**：这次回答为什么漏了关键信息？检索命中了什么？ | 「看日志吧」 | **原生内置 Trace/Span 观测**，每次问答的 embedding→检索→LLM 每一步耗时/命中/花费都在界面上 |
| **存储不一致没底**：MySQL 里的 chunk 和 Milvus 里的向量对不上 | 「祈祷」 | **内置对账工具**，一键扫描漂移文档 |

> **一句话：别人帮你「接入」知识库，EverKB 帮你「养」知识库。**

## 核心特性

- 📄 **多格式文档管线**：Word / PDF / Excel / TXT / Markdown / CSV / HTML + 网页链接，统一解析为 Markdown → 切块 → 向量化，状态机驱动、失败可重试
- ✏️ **Markdown 即内容真相**：解析产物可在后台在线编辑，保存后自动重新切块 + 向量化（跳过重复解析）
- 🔍 **检索问答 + 引用溯源**：按应用挂载多个知识库，SSE 流式返回回答 + 引用卡片（doc / chunk / 页码 / 分数 / 原文链接）
- 📈 **平台概况驾驶舱**：首页 KPI 卡片（知识库/文档/Chunk/应用/问答/花费）+ 近 14 天问答趋势 + 检索模式分布 + 文档状态分布 + 异常告警，卡片可点击下钻
- 📊 **原生全链路可观测**：每次问答自动埋点 Span 成链，后台 Trace 查看器展示 Span 树 + 聚合分析（最慢调用 Top N、各阶段 P95 耗时）
- 🔀 **BM25 混合检索**：向量语义 + 关键词（jieba 分词 + 手写 BM25）双路检索，RRF 倒数排名融合，法条/专有名词检索更准
- 🧪 **检索评测与消融实验**：合成评测集 + Recall@k / MRR / Hit@k 指标，一键跑「纯向量 vs 纯 BM25 vs 混合」对比报告
- 🧹 **对账工具**：扫描「已完成」文档的漂移（chunk 未向量化 / MySQL 与 Milvus 数量不一致）
- 🔌 **可插拔模型**：LLM 与 Embedding 全走 OpenAI 兼容协议，豆包 / 通义 / DeepSeek / Ollama 均可即插即用
- 🗄️ **可插拔存储**：本地磁盘（默认，开箱即跑）/ 阿里云 OSS
- 🔐 **应用级 API Key**：每个问答应用独立 key，创建 / 重置时一次性展示明文，其余脱敏

## 检索评测

EverKB 不只「有」检索能力，还用一套可复现的评测工程**量化**了它。基于 12 部「网络安全与数据合规」法规（233 chunk）构建合成评测集（90 条，seed=42），对三种检索方式做消融实验：

| 检索方式 | Recall@5 | MRR | Hit@5 |
|---|---|---|---|
| 纯向量（Milvus COSINE） | 84.4% | 0.633 | 84.4% |
| 纯 BM25（jieba 分词） | 71.1% | 0.518 | 71.1% |
| **RRF 混合** | **87.8%** | **0.675** | **87.8%** |

**结论**：混合检索在召回与排序上均优于任意单路——向量补足语义改写，BM25 补足专有名词/法条精确命中，RRF 倒数排名融合让两者互补而非冲突。完整实验（方法、局限、复现步骤）见 [检索评测报告](docs/2026-11-19-检索评测报告.md)。

> 管理后台「检索评测」页可直接查看三路指标对比图（数据源 `data/legal/ablation_result.json`，由 `run_ablation.py` 自动生成），无需读文档。

```bash
python scripts/fetch_legal_corpus.py   # 抓取 12 部法规 → data/legal/
python scripts/seed_eval_kb.py         # 建评测库 kb-eval-legal 并入库（233 chunk）
python scripts/build_eval_set.py       # 真实 LLM 合成评测集（90 条）
python scripts/run_ablation.py         # 三路消融跑分 → 生成评测报告 + ablation_result.json
```

## 架构

```
┌─────────────────────────────────────────────────┐
│                 单机 Docker Compose              │
│                                                 │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   │
│  │ FastAPI  │──▶│  MySQL   │   │  Milvus  │   │
│  │  后端     │   │ (元数据)  │   │ (向量)   │   │
│  │  Worker  │   └──────────┘   └──────────┘   │
│  └────┬─────┘        ▲              ▲          │
│       │              │              │          │
│  ┌────▼─────┐   ┌────┴──────┐  ┌────┴──────┐   │
│  │ Vue 管理 │   │ 文档/Chunk │  │ 向量索引   │   │
│  │ 后台     │   │ 双写一致性  │  │ 对账扫描   │   │
│  └──────────┘   └───────────┘  └───────────┘   │
│                                                 │
│  存储(可插拔)          LLM/Embedding(可插拔)      │
│  本地磁盘 / OSS        豆包 / 通义 / DeepSeek      │
│                        / Ollama (OpenAI兼容)     │
└─────────────────────────────────────────────────┘
```

**问答链路（每次问答自动埋点成 Trace）**

```
问题 → [embedding] → [retrieval 检索] → [db 文档确认] → [llm 流式生成] → 回答 + 引用
         └─────┴──────┴──────┴─────── 全部 Span 成链，落库可回看 ──────┘
```

**入库链路（文档解析管线同样纳入观测）**

```
文档上传 → [parse 解析] → [chunking 切块] → [embedding 嵌入] → [vector_insert 向量入库]
               └─────┴──────┴──────┴─────── 管线 Span 成链，Trace 查看器「入库链路」tab 可看 ──────┘
```

## 快速开始

### 前置依赖

- Docker + Docker Compose
- Python 3.11+
- Node.js 18+（前端）
- 一个 OpenAI 兼容的 LLM / Embedding 服务（豆包 / 通义 / DeepSeek / Ollama 均可）

### 1. 启动中间件（MySQL + Milvus + Redis）

```bash
cp .env.example .env          # 填写你的密钥
docker compose up -d          # 启动 MySQL(3307) + Milvus(19530) + Redis(6379)
```

### 2. 启动后端

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python3 scripts/seed_admin.py          # 创建管理员账号
bash scripts/run_backend.sh            # 启动于 http://localhost:8000
```

### 3. 启动前端（管理后台 + 用户对话端）

```bash
cd admin && pnpm install && pnpm dev     # 管理后台
cd web   && pnpm install && pnpm dev     # 用户对话端
```

### 4. 体验完整链路

1. 登录管理后台 → 创建知识库 → 上传文档（等待状态机跑到「已完成」）
2. 创建「应用」→ 挂载知识库 → 复制 api_key
3. 打开用户对话端 → 填入 appId + apiKey → 发起问答
4. 看到 SSE 流式回答 + 引用卡片 → 回到管理后台看 **问答记录 + Trace 树 + 聚合分析**

> 一键冒烟验证：`python3 scripts/smoke_e2e_qa.py --password '你的admin密码'`

## 项目结构

```
everkb/
├── backend/          # FastAPI 后端（REST + SSE + Worker）
│   ├── app/
│   │   ├── api/      #   路由层（admin 管理端 + open 问答端）
│   │   ├── services/ #   pipeline 解析管线 / rag 检索 / trace 埋点 / llm 抽象
│   │   ├── models.py #   SQLAlchemy 2.0 模型
│   │   └── schemas.py#   Pydantic 契约
│   └── tests/        #   248 个测试（pytest）
├── admin/            # Vue3 + Element Plus 管理后台
├── web/              # Vue3 用户对话端（含 chat-kit 对话核心组件）
├── docs/             # 设计文档 / 技术决策记录 / 排期
├── scripts/          # 启动 / 冒烟 / 环境校验脚本
└── docker-compose.yml# MySQL + Milvus + Redis 编排
```

## 测试

```bash
# 后端（248 个用例）
cd backend && pytest

# 前端（32 个用例，含架构边界测试）
cd web && pnpm test
```

## Roadmap

- [x] 多格式文档管线（状态机 + 重试）
- [x] Markdown 在线编辑 + 自动重切块
- [x] SSE 流式问答 + 引用溯源
- [x] 全链路 Trace 观测（Span 树 + 聚合）
- [x] 对账工具
- [x] BM25 混合检索（RRF 融合，jieba 分词 + 手写 BM25）
- [x] 评测问答集跑分（合成评测集 + 检索消融实验，见 [检索评测报告](docs/2026-11-19-检索评测报告.md)）
- [ ] Agent 编排引擎（多步推理，复用观测模型）
- [ ] OCR（扫描件 PDF）
- [ ] OTLP 导出（对接 Jaeger / Langfuse）

## License

[Apache License 2.0](LICENSE)

---

<p align="center">
  <sub>Built with FastAPI + Vue 3 · 让知识库「养」得长久，而不是「丢」进去就完事</sub>
</p>
