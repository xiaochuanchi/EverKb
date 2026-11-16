# EverKB 用户前端（web）

Vue 3 + Vite 单页应用，面向最终用户，产品侧唯一界面：**问答 + 引用展示**（调用 `POST /api/apps/{app_id}/chat`，SSE 流式返回，流结束接收 grounded 与 citations）。不提供文档管理能力（设计文档 §2.4 非目标）。

- 工程尚未初始化；待 Plan 2（问答链路 + Trace 埋点）API 就绪后启动
- 与 [`admin/`](../admin/README.md) 各自独立 package.json，不上 monorepo workspace
