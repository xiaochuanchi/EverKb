<script setup lang="ts">
import { computed, ref } from "vue";
import { getActivePinia } from "pinia";
import { useRouter } from "vue-router";

import { ChatKit } from "@/chat-kit";
import { useAuthStore } from "@/stores/auth";

/**
 * 对话页（F3/Task 32）：门户壳接线 ChatKit。
 *
 * 应用标识来源（B 端 embed 场景典型做法）：
 * 1. URL query 优先（?appId=1&apiKey=sk-xxx，供 embed iframe / 分享链接）；
 * 2. 否则回落到本地配置（localStorage 记住上次填写的 appId/apiKey）。
 * 都不存在时展示配置面板让用户填写。
 *
 * 架构边界：本页是门户壳，可 import element-plus / @/stores / @/chat-kit；
 * 反向耦合（chat-kit → 门户壳）由 tests/architecture.spec.ts 禁止。
 */
const auth = useAuthStore();
const router = useRouter();
const pinia = getActivePinia();

const CONFIG_KEY = "everkb_web_app_config";
// 产品版本号（vite define 注入；模板直用全局常量过不了 vue-tsc）
const appVersion = __APP_VERSION__;

function readStored(): { appId: number; apiKey: string } | null {
  try {
    const raw = localStorage.getItem(CONFIG_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as { appId?: unknown; apiKey?: unknown };
    if (typeof parsed.appId === "number" && typeof parsed.apiKey === "string") {
      return { appId: parsed.appId, apiKey: parsed.apiKey };
    }
  } catch {
    // 解析失败走配置面板
  }
  return null;
}

function queryConfig(): { appId: number; apiKey: string } | null {
  const q = new URLSearchParams(window.location.search);
  const appIdRaw = q.get("appId");
  const apiKey = q.get("apiKey");
  if (!appIdRaw || !apiKey) return null;
  const appId = Number(appIdRaw);
  if (Number.isNaN(appId) || appId <= 0) return null;
  return { appId, apiKey };
}

const effective = computed(() => queryConfig() ?? readStored());

// 配置面板（无有效配置时展示）
const showConfig = ref(effective.value === null);
const appIdInput = ref(effective.value ? String(effective.value.appId) : "");
const apiKeyInput = ref(effective.value ? effective.value.apiKey : "");

const resolved = computed(() => {
  if (effective.value) return effective.value;
  const appId = Number(appIdInput.value);
  const apiKey = apiKeyInput.value.trim();
  if (Number.isNaN(appId) || appId <= 0 || !apiKey) return null;
  return { appId, apiKey };
});

function applyConfig(): void {
  const cfg = resolved.value;
  if (!cfg) return;
  try {
    localStorage.setItem(CONFIG_KEY, JSON.stringify(cfg));
  } catch {
    // 无痕模式静默降级，仅本次会话生效
  }
  showConfig.value = false;
}

function handleLogout(): void {
  auth.clear();
  void router.push({ name: "login" });
}
</script>

<template>
  <main class="chat-page">
    <!-- 顶栏 -->
    <header class="chat-header">
      <div class="chat-brand">EverKB 对话 <span class="chat-version">v{{ appVersion }}</span></div>
      <div class="chat-header-right">
        <span v-if="effective" class="chat-app-tag">应用 #{{ effective.appId }}</span>
        <button type="button" class="chat-logout" @click="handleLogout">退出登录</button>
      </div>
    </header>

    <!-- 配置面板（无 appId/apiKey 时） -->
    <section v-if="showConfig" class="chat-config">
      <h2>连接知识库应用</h2>
      <p class="config-hint">
        请输入要对话的应用 ID 与 API Key（在管理后台「应用管理」创建应用后获取）。
      </p>
      <input v-model="appIdInput" class="config-input" type="number" min="1" placeholder="应用 ID（appId）" />
      <input v-model="apiKeyInput" class="config-input" type="text" placeholder="API Key（sk-...）" />
      <button type="button" class="config-submit" :disabled="!resolved" @click="applyConfig">连接</button>
    </section>

    <!-- 对话核心 -->
    <section v-else class="chat-body">
      <ChatKit
        v-if="effective"
        :pinia="pinia!"
        :options="{ appId: effective.appId, apiKey: effective.apiKey }"
      />
    </section>
  </main>
</template>

<style scoped>
.chat-page {
  display: flex;
  flex-direction: column;
  height: 100vh;
  min-height: 0;
}

.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 20px;
  border-bottom: 1px solid var(--el-border-color-light, #ebeef5);
  flex-shrink: 0;
}

.chat-brand {
  font-size: 16px;
  font-weight: 600;
}

.chat-version {
  font-size: 12px;
  font-weight: 400;
  color: var(--el-text-color-secondary, #909399);
}

.chat-header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.chat-app-tag {
  font-size: 12px;
  color: var(--el-text-color-secondary, #909399);
}

.chat-logout {
  border: 1px solid var(--el-border-color, #dcdfe6);
  background: #fff;
  color: var(--el-text-color-regular, #606266);
  padding: 5px 14px;
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
}

.chat-logout:hover {
  color: var(--el-color-primary, #409eff);
  border-color: var(--el-color-primary, #409eff);
}

.chat-body {
  flex: 1;
  min-height: 0;
  display: flex;
}

.chat-body > * {
  flex: 1;
}

.chat-config {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 24px;
}

.chat-config h2 {
  margin: 0;
  font-size: 20px;
}

.config-hint {
  margin: 0 0 8px;
  font-size: 13px;
  color: var(--el-text-color-secondary, #909399);
  text-align: center;
  max-width: 420px;
  line-height: 1.6;
}

.config-input {
  width: 320px;
  max-width: 90%;
  border: 1px solid var(--el-border-color, #dcdfe6);
  border-radius: 8px;
  padding: 10px 12px;
  font-size: 14px;
  outline: none;
}

.config-input:focus {
  border-color: var(--el-color-primary, #409eff);
}

.config-submit {
  width: 320px;
  max-width: 90%;
  border: none;
  background: var(--el-color-primary, #409eff);
  color: #fff;
  padding: 10px;
  border-radius: 8px;
  font-size: 14px;
  cursor: pointer;
}

.config-submit:disabled {
  background: #a0cfff;
  cursor: not-allowed;
}
</style>
