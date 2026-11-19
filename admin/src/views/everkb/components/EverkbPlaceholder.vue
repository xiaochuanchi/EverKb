<script setup lang="ts">
  /**
   * EverKB 业务页面占位组件
   * 批次 1/2 按排期逐页替换实现
   * 用法：<EverkbPlaceholder :title="t('menus.everkb.knowledge')" />
   */
  defineProps<{
    title: string
    description?: string
  }>()
</script>

<template>
  <div class="everkb-placeholder">
    <div class="placeholder-card">
      <h2>{{ title }}</h2>
      <el-empty :description="description || $t('everkb.placeholder.underConstruction')" />
    </div>
  </div>
</template>

<style lang="scss" scoped>
  .everkb-placeholder {
    padding: 16px;

    .placeholder-card {
      background: var(--art-main-bg-color);
      border-radius: 8px;
      padding: 24px;
      min-height: 60vh;

      h2 {
        margin: 0 0 16px;
        font-size: 20px;
      }
    }
  }
</style>
