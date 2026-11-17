# chat-kit · 对话核心组件包（占位）

**边界铁律**（排期文档 §3 P0 架构约束）：对话核心必须与门户壳解耦，为 F10 embed widget 保持独立可挂载。

## 允许依赖

- `vue` / `pinia`（独立实例，由挂载方传入）
- 类型定义（`src/api/types.ts` 的 ApiError 等）
- API 访问：**只允许注入**（挂载方传入实现了 `ApiClient` 或流式处理器的对象）

## 禁止依赖（由 tests/architecture.spec.ts 固化）

- `@/router`、`@/views`、`@/stores`、`@/layouts` —— 门户壳专属
- `@/api/index`（API 单例）—— 挂载方注入，不得反向耦合门户壳
- `element-plus` —— embed widget 场景需独立打包，重组件库不出现在 kit 内

F3 开工时，本目录从"占位"升级为：消息气泡、SSE 流式渲染、引用溯源卡片、chat-kit 专属 store。
