<template>
  <div class="reconcile-page">
    <!-- 工具条：说明 + 重新扫描 -->
    <div class="toolbar art-card-sm">
      <div class="toolbar-left">
        <ElTooltip
          content="扫描状态为「已完成」的文档，检测 chunk 未向量化或 MySQL/Milvus 数量不一致的漂移。"
          placement="bottom"
        >
          <el-icon class="toolbar-info"><InfoFilled /></el-icon>
        </ElTooltip>
        <span class="toolbar-label">向量漂移扫描</span>
        <ElTag
          v-if="!loading"
          size="small"
          :type="items.length ? 'danger' : 'success'"
          effect="plain"
        >
          {{ items.length ? `发现 ${items.length} 项漂移` : '无漂移' }}
        </ElTag>
      </div>

      <div class="toolbar-right">
        <ElButton type="primary" :loading="loading" @click="scan">
          <el-icon style="margin-right: 4px"><Refresh /></el-icon>
          重新扫描
        </ElButton>
      </div>
    </div>

    <!-- 漂移清单 -->
    <ArtTable
      :columns="columns"
      :data="data"
      :loading="loading"
      empty-height="420"
      emptyText="未发现向量漂移"
    >
      <template #doc_id="{ row }">
        <ElButton link type="primary" @click="goDocument(row.doc_id)"> #{{ row.doc_id }}</ElButton>
      </template>
      <template #issue="{ row }">
        <ElTag size="small" :type="ISSUE_META[row.issue]?.tag || 'info'" effect="plain">
          {{ ISSUE_META[row.issue]?.label ?? row.issue }}
        </ElTag>
      </template>
    </ArtTable>
  </div>
</template>

<script setup lang="ts">
  import { InfoFilled, Refresh } from '@element-plus/icons-vue'
  import { fetchReconciliation } from '@/api/everkb/reconcile'
  import type { ColumnOption } from '@/types/component'

  defineOptions({ name: 'EverKBReconcile' })

  type ReconcileRow = Api.EverKB.ReconciliationItem

  const ISSUE_META: Record<string, { label: string; tag: 'danger' | 'warning' | 'info' }> = {
    unvectorized: { label: 'chunk 未向量化', tag: 'warning' },
    count_mismatch: { label: '向量数量不一致', tag: 'danger' }
  }

  const loading = ref(false)
  const items = ref<ReconcileRow[]>([])

  const columns: ColumnOption<ReconcileRow>[] = [
    { prop: 'doc_id', label: '文档 ID', width: 120, useSlot: true },
    { prop: 'issue', label: '漂移类型', width: 200, useSlot: true }
  ]

  const data = computed(() => items.value)

  const scan = async () => {
    loading.value = true
    try {
      items.value = await fetchReconciliation()
    } catch {
      // http 层已弹错误
    } finally {
      loading.value = false
    }
  }

  const goDocument = (docId: number) => {
    window.open(`/everkb/document#doc=${docId}`, '_blank')
  }

  onMounted(() => {
    void scan()
  })
</script>

<style lang="scss" scoped>
  .reconcile-page {
    padding: 16px;

    .toolbar {
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 8px;
      padding: 12px 16px;
      margin-bottom: 12px;

      .toolbar-left,
      .toolbar-right {
        display: flex;
        align-items: center;
        gap: 10px;
      }

      .toolbar-info {
        color: var(--art-gray-600, #888);
        cursor: help;
      }

      .toolbar-label {
        font-size: 14px;
        font-weight: 600;
      }
    }
  }
</style>
