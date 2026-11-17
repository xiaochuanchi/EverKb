# EverKB 用户前端（web）

Vue 3 + Vite 单页应用，面向最终用户，产品侧唯一界面：**问答 + 引用展示**（调用 `POST /api/apps/{app_id}/chat`，SSE 流式返回，流结束接收 grounded 与 citations）。不提供文档管理能力（设计文档 §2.4 非目标）。

- 与 [`admin/`](../admin/README.md) 各自独立 package.json，不上 monorepo workspace
- 需求与排期基线：[`docs/2026-11-17-web前端-技术栈与功能需求排期.md`](../docs/2026-11-17-web前端-技术栈与功能需求排期.md)
- 后端契约：API 统一信封见 [`docs/2026-11-17-api统一信封-设计文档.md`](../docs/2026-11-17-api统一信封-设计文档.md)

## 技术栈

Vue 3（`<script setup>`）+ TypeScript + Vite + Pinia + Vue Router + Element Plus + Axios。SSE 流式用原生 fetch（F3）。

## 常用命令

```bash
pnpm install   # 安装依赖
pnpm dev       # 开发服务器（5173，/api 代理到本机 FastAPI，目标由 VITE_DEV_PROXY_TARGET 控制）
pnpm test      # 单测（Vitest，全进程内 Fake，不出网）
pnpm build     # 类型检查 + 产物构建
```

## 目录结构

```
src/
  api/          # 信封解包、Axios 封装（统一弹错 + 401 重新登录对话）、全局单例（门户壳专属）
    modules/    # API 模块层：按业务域一个文件、函数式导出、注释即接口文档（借鉴 pengYanBPM）
  chat-kit/     # 对话核心组件包：与门户壳解耦，依赖只许注入（F10 embed widget 前置约束）
  router/       # 路由 + 守卫壳
  stores/       # Pinia（auth store）
  views/        # 页面
tests/          # Vitest：信封 / 客户端拦截器 / chat-kit 架构边界
```

## 当前进度

- [x] P0-F0 工程基建（脚手架 / 信封封装 / dev 代理 / 路由守卫壳）
- [ ] P0-F1 登录（等后端 auth API，当前为本地开发令牌占位）
- [ ] P0-F2 布局壳 / F3 对话页 / F4 引用溯源 / F5 会话管理 / F6 反馈
