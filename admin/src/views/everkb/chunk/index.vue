<script setup lang="ts">
  import { useI18n } from 'vue-i18n'
  import EverkbPlaceholder from '../components/EverkbPlaceholder.vue'

  const { t } = useI18n()
</script>

<template>
  <EverkbPlaceholder :title="t('menus.everkb.chunk')" />
</template>
