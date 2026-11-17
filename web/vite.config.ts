/// <reference types="vite/client" />

import { fileURLToPath, URL } from "node:url";

import vue from "@vitejs/plugin-vue";
import { defineConfig, loadEnv } from "vite";

/**
 * dev 代理：前端请求 /api/** 转发到本机 FastAPI（uvicorn 默认 8000）。
 * 目标地址由 VITE_DEV_PROXY_TARGET 控制（见 .env.development / .env.example）。
 * 注意：将来接问答 SSE 时，代理需追加 `buffer: false` 关闭代理缓冲（见排期文档 §6 风险 1）。
 */
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "VITE_");
  return {
    plugins: [vue()],
    resolve: {
      alias: {
        "@": fileURLToPath(new URL("./src", import.meta.url)),
      },
    },
    server: {
      port: 5173,
      proxy: {
        "/api": {
          target: env.VITE_DEV_PROXY_TARGET || "http://localhost:8000",
          changeOrigin: true,
        },
      },
    },
  };
});
