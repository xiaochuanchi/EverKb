import { fileURLToPath, URL } from "node:url";

import { defineConfig } from "vitest/config";

/**
 * 单测配置：node 环境即可（信封解包 / 客户端拦截器 / 架构边界均为纯逻辑，
 * 不出网红线在测试侧的实现——全部用 Fake 适配器，不发任何真实请求）。
 */
export default defineConfig({
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  test: {
    environment: "node",
    include: ["tests/**/*.spec.ts"],
  },
});
