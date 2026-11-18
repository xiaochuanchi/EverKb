# EverKB API 层（src/api/everkb/）

对接 FastAPI 后端的 REST API 封装。类型契约见 `../types/api/api.d.ts`（`Api.EverKB` 命名空间，snake_case 对齐 `backend/app/schemas.py`）。

> 知识库与文档的 API 封装在 `src/api/kb.ts` 与 `src/api/document.ts`（历史沿革），本目录收敛其余资源。

| 文件 | 资源 | 主要接口 |
|---|---|---|
| `app.ts` | 应用 | 列表 / 创建（明文 api_key）/ PATCH 更新 / 删除 / 重置密钥 |
| `chunk.ts` | Chunk | 单文档分页列表（按 chunk_index 升序） |
| `qa-record.ts` | 问答记录 | 分页（app_id/feedback 筛选）/ 详情（含 citations） |
| `trace.ts` | Trace | span 树（后端已组树）/ 跨 Trace 聚合（最慢 Top N + P95） |
| `reconcile.ts` | 对账 | 漂移扫描（unvectorized / count_mismatch 清单） |

## 接口契约要点

- **前缀**：所有 admin 接口统一 `/api/v1/admin`（鉴权用 JWT Bearer，http 拦截器自动加）。
- **信封**：后端返回 `{code, message, data}`，`code==0` 成功；http 层已解包（`request.get<T>` 返回 `data`）。
- **HTTP 动词**：更新用 `PATCH`（局部更新，未传字段不修改），删除 `DELETE`，创建 `POST`。
- **trace 列表入口**：复用 `/records`（qa_record 即一条 Trace 主表）；span 树由后端 `/traces/{record_id}` 直接组好，前端只递归渲染。

## SSE 问答（open 侧，非本目录职责）

问答 chat 接口 `POST /api/v1/apps/{app_id}/chat` 为 SSE 流式（X-API-Key 鉴权，退出统一信封），**不走本层 axios 封装**。由 web 用户前端消费（原生 `fetch` + `ReadableStream` 逐帧解析），见 `web/src/chat-kit/`。
