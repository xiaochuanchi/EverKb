# EverKB API 层（src/api/everkb/）

对接 FastAPI 后端的 REST API 封装。类型契约见 `../types/api/everkb.d.ts`（对齐设计文档 §5 数据模型）。

| 文件 | 资源 | 主要接口 |
|---|---|---|
| `kb.ts` | 知识库 | CRUD / 启停（仅空库可删） |
| `document.ts` | 文档 | 上传（multipart）/ 批量 URL / 替换重传 / 重试 / 启停 / 删除 / content.md 读写 / 原文签名 URL |
| `chunk.ts` | Chunk | 分页列表 / 按文档全量 |
| `app.ts` | 应用 | CRUD（挂载 KB、top_k、阈值、Prompt、模型参数） |
| `qa-record.ts` | 问答记录 | 分页 / 详情（含引用）/ 反馈 / 反馈统计 |
| `trace.ts` | Trace | 列表 / Span 全集（前端组树）/ 跨 Trace 聚合 |
| `reconcile.ts` | 对账 | 漂移扫描 / 一键重建 |

## 与后端对接的两个待对齐点（批次 1 接线时确认）

1. **响应包装**：http 层（`src/utils/http/index.ts`）按 `{code: 200, msg, data}` 解包。FastAPI 默认裸 JSON + HTTP 状态码，届时二选一：后端加统一包装、或前端 http 层加适配（建议后端包装，保持模板能力不损失）。
2. **鉴权头**：拦截器发 `Authorization: <token>`（无 Bearer 前缀）。FastAPI JWT 标准是 `Bearer <token>`，接线时在前端加前缀或后端兼容解析。
3. **路径为预估**：以上 URL 按设计文档 §8 的 api 模块命名预估（`/api/kbs`、`/api/documents`…），以后端实际路由为准微调，函数签名与类型不变。

## SSE 问答调试

问答 chat 接口为 SSE 流式（`POST /api/apps/{app_id}/chat`），不走本层 axios 封装；批次 1 需补装 `@microsoft/fetch-event-source` 处理（同时解决原生 EventSource 不支持 POST + 自定义头的问题）。
