<script setup lang="ts">
  import { useI18n } from 'vue-i18n'
  import { useRoute } from 'vue-router'
  import EverkbPlaceholder from '../components/EverkbPlaceholder.vue'

  const { t } = useI18n()
  const route = useRoute()
  const traceId = route.query.traceId as string | undefined
</script>

<template>
  <EverkbPlaceholder
    :title="t('menus.everkb.traceDetail')"
    :description="traceId ? `Trace #${traceId} 的 Span 树 + 时间轴（批次 1 实现，演示灵魂页面）` : '缺少 traceId 参数'"
  />
</template>
