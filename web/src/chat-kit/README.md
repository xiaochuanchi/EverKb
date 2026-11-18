# chat-kit · 对话核心组件包（F3 已落地）

**边界铁律**（排期文档 §3 P0 架构约束）：对话核心必须与门户壳解耦，为 F10 embed widget 保持独立可挂载。

## 允许依赖

- `vue` / `pinia`（独立实例，由挂载方传入）
- 类型定义（`src/chat-kit/types.ts` 的纯类型契约）
- API 访问：**只允许注入**（挂载方传入 `ChatKitOptions`，含 appId / apiKey；流式经内置 `sse.ts` 原生 fetch，不 import axios）

## 禁止依赖（由 tests/architecture.spec.ts 固化）

- `@/router`、`@/views`、`@/stores`、`@/layouts` —— 门户壳专属
- `@/api/index`（API 单例）—— 挂载方注入，不得反向耦合门户壳
- `element-plus` —— embed widget 场景需独立打包，重组件库不出现在 kit 内

## 目录结构（F3）

| 文件 | 职责 |
|---|---|
| `types.ts` | 纯类型契约（ChatMessage / Citation / ChatStreamEvent / ChatKitOptions / StreamHandlers） |
| `sse.ts` | SSE 流式客户端（`parseSseBuffer` 帧解析 + `streamChat` fetch 流式），可注入 fetch 测试 |
| `store.ts` | `useChatStore`（defineStore）+ `createChatStore(pinia)` 独立实例工厂 + `createSender` 发起问答 |
| `ChatKit.vue` | 对话核心组件（气泡 / 打字机流式 / 引用溯源卡片 / 输入框），props 注入 pinia + options |
| `index.ts` | 统一出口 |

## 挂载方式（门户壳 / embed widget 通用）

```ts
// 门户壳：传入其全局 pinia
import { ChatKit } from "@/chat-kit";
// <ChatKit :pinia="pinia" :options="{ appId, apiKey }" />

// embed widget：传入自有 createPinia() 实例，与门户壳隔离
import { createPinia } from "pinia";
import { ChatKit } from "@/chat-kit";
// <ChatKit :pinia="createPinia()" :options="{ appId, apiKey }" />
```

## SSE 协议（对齐 backend/app/api/open.py）

- 请求：`POST /api/v1/apps/{app_id}/chat`，头 `X-API-Key`，体 `{ question, user_key }`
- 帧：`data: {json}\n\n`，事件 `{ delta }` 增量 → 收尾 `{ grounded, citations }`
- citations 元素：`doc_name / doc_id / chunk_id / page_number / snippet / score / source_url`
