# EverKB 管理后台（admin）

EverKB（RAG 知识库管理平台）的运营管理后台，Vue 3 + TypeScript + Vite + Element Plus 单页应用。

> **二次开发声明**：本项目基于开源模板 [art-design-pro](https://github.com/Daymychen/art-design-pro) 3.0.2（MIT License）构建，上游版权声明见 [`LICENSE`](./LICENSE)。按 EverKB 需求裁剪了演示层与动态权限，业务代码集中在 `src/views/everkb/`、`src/api/`、`src/router/modules/everkb.ts`。

## 定位

面向平台管理员/运营者，仅消费后端 REST/SSE API，不直连 MySQL / Milvus。页面清单见 [`../docs/2026-11-14-rag知识库管理平台-设计文档.md`](../docs/2026-11-14-rag知识库管理平台-设计文档.md) §7：

- 登录（JWT）
- 知识库管理、文档管理（状态机）、md 编辑器（content.md）、chunk 查看
- 应用管理、问答记录
- **Trace 查看器**（Span 树 + 时间轴，求职演示核心页）
- 对账工具

规划与排期：

- 技术选型：[`../docs/2026-11-17-admin-技术选型与规划.md`](../docs/2026-11-17-admin-技术选型与规划.md)（已拍板）
- 实施排期：[`../docs/2026-11-17-admin-实施排期与路径.md`](../docs/2026-11-17-admin-实施排期与路径.md)

## 环境要求

- Node.js ≥ 20.19
- pnpm ≥ 8.8

```bash
# 安装依赖
pnpm install

# 本地开发（代理指向 FastAPI，见 .env.development）
pnpm dev

# 生产构建（含 vue-tsc 类型检查）
pnpm build
```
