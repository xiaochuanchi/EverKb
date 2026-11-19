# 贡献指南（Contributing）

感谢你有兴趣为 EverKB 做贡献！这是一份面向外部贡献者的指南，说明如何搭建开发环境、遵守项目约定、提交代码与发起 Pull Request。

在动手之前，建议先读一遍 [README](README.md) 了解项目定位与架构总览。

---

## 目录

- [行为准则](#行为准则)
- [我能贡献什么](#我能贡献什么)
- [开发环境搭建](#开发环境搭建)
- [项目结构与约定](#项目结构与约定)
- [提交规范](#提交规范)
- [测试要求](#测试要求)
- [Pull Request 流程](#pull-request-流程)
- [Issue 与沟通](#issue-与沟通)

---

## 行为准则

我们希望 EverKB 社区是友好、包容、互相尊重的：

- 对事不对人，聚焦技术讨论，不做人身攻击。
- 尊重不同背景、经验水平的参与者，耐心解答新手问题。
- 不发布与项目无关的广告、垃圾信息或政治敏感内容。

遇到违反上述原则的行为，请在 Issue 中 @维护者处理。

---

## 我能贡献什么

以下类型的贡献最受欢迎，欢迎挑选你感兴趣的方向：

| 类型 | 示例 |
|---|---|
| 🐛 **Bug 修复** | 复现问题 → 定位 → 修复 → 补测试 |
| ✨ **新特性** | 新的解析器、存储后端、检索策略、观测能力 |
| 🔌 **模型 / 存储适配** | 接入新的 OpenAI 兼容模型厂商、新的对象存储后端 |
| 📝 **文档** | 修正 / 补充 README、代码注释 |
| 🧪 **测试与评测** | 补测试用例、扩充评测集、跑消融实验 |
| 🌐 **国际化** | 补充 `admin` / `web` 的 i18n 词条 |

> ⚠️ 不确定方向时，**先开 Issue 讨论**再动手，避免白费功夫。尤其涉及架构层面的改动（新增依赖、改表结构、改公共抽象）务必先沟通。

---

## 开发环境搭建

完整启动步骤见 [README·快速开始](README.md#快速开始)，此处只列贡献者最常用的命令。

### 前置依赖

- Python 3.11+（CI 使用 3.13）
- Node.js 20+、pnpm 8+
- Docker + Docker Compose（跑 MySQL / Milvus / Redis 中间件）
- 一个 OpenAI 兼容的 LLM / Embedding 服务（本地开发可用 Ollama）

### 后端

```bash
# 1. 起中间件
docker compose up -d

# 2. 虚拟环境 + 依赖
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 3. 初始化管理员（首次）
python3 scripts/seed_admin.py

# 4. 启动开发服务器
uvicorn app.main:app --reload --app-dir backend
```

### 前端

```bash
cd admin && pnpm install && pnpm dev    # 管理后台
cd web   && pnpm install && pnpm dev    # 用户对话端
```

### 运行测试

```bash
# 后端（全量，仓库根执行）
pytest

# 前端（web，含架构边界测试）
cd web && pnpm test

# admin 无单测，跑 lint + 构建
cd admin && pnpm lint && pnpm build
```

> 后端测试**不出网**：vector / embedder 一律注入 Fake，无需启动 MySQL / Milvus / Redis，也不需要真实 API Key。

---

## 项目结构与约定

```
everkb/
├── backend/          # FastAPI 后端（REST + SSE + Worker）
│   ├── app/
│   │   ├── api/      #   路由层（admin 管理端 + open 问答端）
│   │   ├── services/ #   pipeline / rag / trace / llm 抽象
│   │   ├── parsers/  #   文档解析器（docx / pdf / xlsx / webpage → Markdown）
│   │   ├── core/     #   基础设施层（config / db / storage 抽象）
│   │   ├── models.py #   SQLAlchemy 2.0 模型
│   │   └── schemas.py#   Pydantic 契约
│   └── tests/        #   pytest（SQLite 内存库 + Fake 双件套，镜像 app 结构）
├── admin/            # Vue3 + Element Plus 管理后台
├── web/              # Vue3 用户对话端（含 chat-kit 对话核心组件）
├── scripts/          # 启动 / 冒烟 / verify 连通性 / 评测脚本
└── docker-compose.yml
```

### 核心红线（务必遵守）

以下约束是本项目经过反复权衡后定下的，PR 若违反会被要求返工：

1. **测试绝不出网**：vector / embedder 一律注入 Fake，禁止在测试里发起真实网络调用。
2. **删除顺序固定**：先删 Milvus 向量 → 再删 MySQL（chunk 行 → doc 行）→ 最后删存储对象。
3. **替换语义**：旧版本向量在新版本完整入库成功前必须持续供检索，成功后才按 old_ids 清理。
4. **不引入重型框架**：不引入 LangChain / LangGraph / Celery / Alembic。
5. **密钥不入库**：`.env` 真实密钥绝不提交；新增 `Settings` 字段必须同步 `.env.example`。
6. **API 只落库翻状态**：实际处理由 worker 线程异步完成（`app/workers.py` → `run_pending`）。

### 代码约定速览

- 后端：FastAPI 同步路由、SQLAlchemy 2.x、依赖注入缝 `create_app(settings, *, storage, embedder, vector, rate_limiter, llm, bm25)`、中文 docstring、状态机常量。
- 业务代码**不直接 import** pymysql / pymilvus / redis 裸驱动，只走 `core` 层封装或 Protocol。
- 路由双前缀：admin 挂 `/api/v1/admin`（JWT），open 挂 `/api/v1`（X-API-Key）。
- 前端：Vue 3 + TypeScript + Pinia + Element Plus + vue-i18n，遵循既有代码风格，ESLint / Prettier / Stylelint 全部通过。
- **抽象阈值**：只在第二个真实使用点出现时才抽离公共层，第一次出现就近实现，不要提前造 utils / 新 Protocol。
- 约定冲突时，以仓库现有代码的行为为准。

---

## 提交规范

本项目前端启用 commitlint（`@commitlint/config-conventional`），提交信息请遵循 [Conventional Commits](https://www.conventionalcommits.org/zh-hans/) 规范：

```
<type>(<scope>): <subject>
```

### type 类型

| type | 含义 |
|---|---|
| `feat` | 新功能 |
| `fix` | Bug 修复 |
| `docs` | 文档变更 |
| `refactor` | 重构（不改变功能） |
| `perf` | 性能优化 |
| `test` | 测试相关 |
| `chore` | 构建 / 工具 / 杂项 |
| `style` | 代码格式（不影响逻辑） |
| `ci` | CI / 流水线变更 |

### scope 建议

`backend` / `admin` / `web` / `docs` / `scripts` / `deps` 等，可按模块细分（如 `backend/pipeline`、`admin/assistant`）。

### 示例

```bash
git commit -m "feat(backend): 新增文档生命周期状态机"
git commit -m "fix(admin): 修复 chunk 路由无 docId 时空白的问题"
git commit -m "docs: 补充模型接入指南"
```

> 提交前请先 `git diff` 自查，确保**没有**把 `.env`、`.venv`、`node_modules`、`*.miora`、品牌源文件等敏感/生成物带入（完整清单见 `.gitignore`）。仓库内的 `data/legal/` 为公开法规文本与评测数据，**保留开源**。

---

## 测试要求

- 后端：所有改动（含 Bug 修复）**必须**有对应的 pytest 用例；新增表/字段需同步覆盖相关测试。测试不出网，使用 `SQLite` 内存库 + Fake embedder / vector 双件套。
- 前端：涉及 `web` 的改动跑 `pnpm test`；`admin` 跑 `pnpm lint && pnpm build` 保证类型与构建通过。
- 全量自测通过后再提交，CI 会按路径增量构建（见 `.github/workflows/ci.yml`）。

---

## Pull Request 流程

1. **Fork** 本仓库，基于 `main` 创建你的分支。
2. 本地完成开发，跑通相关测试。
3. 提交时遵循[提交规范](#提交规范)。
4. 推送分支并发起 Pull Request。

### PR 描述请包含

- **做了什么**：一句话说明改动意图。
- **为什么这么做**：背景与动机，关联的 Issue 编号（如有）。
- **怎么验证**：跑了哪些测试 / 手测步骤、截图或日志。
- **影响范围**：是否改动表结构、公共接口、依赖、`.env.example` 等。

### 评审与合并

- 维护者会在合理时间内 review，可能需要你来会往返修改。
- CI 必须全绿（backend pytest + admin lint/build + web build/test）。
- 合并策略以维护者为准；建议在 PR 中勾选「allow maintainer edits」。

> 小提示：**先开 Issue 讨论，再开 PR**，能显著提高一次通过的几率。

---

## Issue 与沟通

- **Bug 报告**：请尽量附上环境信息（OS / Python / Node 版本）、复现步骤、期望 vs 实际行为、相关日志或截图。
- **功能建议**：说明使用场景、期望行为，欢迎附带方案草图。
- **问题求助**：先搜索已有 Issue，避免重复提问。

沟通语言不限，中文 / English 皆可。

---

再次感谢你的贡献！🫡
