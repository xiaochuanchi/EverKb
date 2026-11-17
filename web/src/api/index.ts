import { ElMessage, ElMessageBox } from "element-plus";

import router from "@/router";
import { useAuthStore } from "@/stores/auth";

import { createApiClient, type ApiClient } from "./client";

/**
 * 全局 API 客户端单例（门户壳装配点）。
 *
 * 提示层借鉴 pengYanBPM（src/utils/request.js）：
 * - 业务 / 网络错误统一弹 ElMessage.error；
 * - 401 弹重新登录对话（取消可停留原页），并用 reloginDialogOpen 标志去重——
 *   BPM 模式的已知痛点是并发请求同时失效会连环弹窗，此处修复。
 *
 * ⚠️ 架构边界：本模块是"门户壳"的一部分，`src/chat-kit/` 禁止 import 本文件
 * （chat-kit 的 API 依赖须以注入方式提供，为 F10 embed widget 保持独立可挂载）。
 * 边界由 tests/architecture.spec.ts 固化执行。
 */
let reloginDialogOpen = false;

export const api: ApiClient = createApiClient({
  getAccessToken: () => useAuthStore().token,
  onUnauthorized: (err) => {
    const auth = useAuthStore();
    auth.clear();
    if (reloginDialogOpen) {
      return; // 已有对话挂起，抑制连环弹窗
    }
    if (router.currentRoute.value.name === "login") {
      return; // 登录页本身返回 401（如密码错误）不弹重新登录对话
    }
    reloginDialogOpen = true;
    ElMessageBox.confirm(`登录状态已失效（${err.message}），请重新登录`, "会话失效", {
      confirmButtonText: "重新登录",
      cancelButtonText: "取消",
      type: "warning",
    })
      .then(() => {
        void router.push({
          name: "login",
          query: { redirect: router.currentRoute.value.fullPath },
        });
      })
      .catch(() => {
        // 取消：停留当前页（与 BPM 行为一致），下次失效会再提示
      })
      .finally(() => {
        reloginDialogOpen = false;
      });
  },
  onBusinessError: (err) => {
    ElMessage.error(err.message);
  },
});
