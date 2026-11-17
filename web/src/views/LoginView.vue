<script setup lang="ts">
import { ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";

import { useAuthStore } from "@/stores/auth";

/**
 * 登录页占位（F0）：auth API 是后端缺口，这里先用"本地开发令牌"打通守卫链路。
 * 后端就绪后改造点：handleLogin 改调 POST /api/v1/auth/login 并 setToken(返回值)。
 */
const auth = useAuthStore();
const route = useRoute();
const router = useRouter();

const username = ref("");
const password = ref("");

function handleLogin(): void {
  if (!username.value.trim()) {
    ElMessage.warning("请输入用户名");
    return;
  }
  if (!password.value) {
    ElMessage.warning("请输入密码");
    return;
  }
  auth.setToken(`dev-token:${username.value.trim()}`);
  ElMessage.success("已写入本地开发令牌（占位，auth API 就绪后替换）");
  const redirect = route.query.redirect;
  void router.push(typeof redirect === "string" ? redirect : { name: "chat" });
}
</script>

<template>
  <main class="login-page">
    <section class="login-card">
      <h1>EverKB</h1>
      <p class="subtitle">B 端客户 Agent 对话门户（开发占位登录）</p>
      <el-input v-model="username" placeholder="用户名" />
      <el-input v-model="password" type="password" show-password placeholder="密码" />
      <el-button type="primary" @click="handleLogin">登录</el-button>
    </section>
  </main>
</template>

<style scoped>
.login-page {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
}
.login-card {
  display: flex;
  flex-direction: column;
  gap: 12px;
  width: 320px;
  padding: 32px;
  border: 1px solid var(--el-border-color);
  border-radius: 8px;
}
.login-card h1 {
  margin: 0;
  font-size: 24px;
  text-align: center;
}
.subtitle {
  margin: 0 0 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  text-align: center;
}
</style>
