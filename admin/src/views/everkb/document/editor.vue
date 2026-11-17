<script setup lang="ts">
  import { useI18n } from 'vue-i18n'
  import { useRoute } from 'vue-router'
  import EverkbPlaceholder from '../components/EverkbPlaceholder.vue'

  const { t } = useI18n()
  const route = useRoute()
  const docId = route.query.docId as string | undefined
</script>

<template>
  <EverkbPlaceholder
    :title="t('menus.everkb.documentEditor')"
    :description="docId ? `编辑文档 #${docId} 的 content.md（批次 2 实现，需补装 md-editor-v3）` : '缺少 docId 参数'"
  />
</template>
