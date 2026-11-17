<script setup lang="ts">
import { useRouter } from "vue-router";

const router = useRouter();
</script>

<template>
  <main class="not-found">
    <h1>404</h1>
    <p>页面不存在</p>
    <el-button link type="primary" @click="router.push({ name: 'chat' })">回到首页</el-button>
  </main>
</template>

<style scoped>
.not-found {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding-top: 120px;
}
</style>
