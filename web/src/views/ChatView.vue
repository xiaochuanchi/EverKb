<script setup lang="ts">
import { useRouter } from "vue-router";

import { useAuthStore } from "@/stores/auth";

/** 对话页占位（F0）：真实对话 UI 属 F3 实现范围，此页先承接守卫链路验证。 */
const auth = useAuthStore();
const router = useRouter();

function handleLogout(): void {
  auth.clear();
  void router.push({ name: "login" });
}
</script>

<template>
  <main class="chat-page">
    <h1>对话（占位）</h1>
    <p>对话核心 UI 在 F3 实现（SSE 流式 + 引用溯源），布局壳在 F2 实现。</p>
    <el-button @click="handleLogout">退出登录</el-button>
  </main>
</template>

<style scoped>
.chat-page {
  padding: 24px;
}
</style>
