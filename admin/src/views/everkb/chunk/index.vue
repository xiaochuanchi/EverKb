<template>
  <div class="chunk-page">
    <!-- 工具条：文档信息 + 返回 -->
    <div class="toolbar art-card-sm">
      <div class="toolbar-left">
        <ElButton link type="primary" @click="goBack">
          <el-icon style="margin-right: 4px"><Back /></el-icon>
          返回文档
        </ElButton>
        <span class="toolbar-divider" />
        <span class="toolbar-label">文档</span>
        <span class="doc-title">{{ docName || `#${docId}` }}</span>
        <ElTag v-if="total > 0" size="small" effect="plain">共 {{ total }} 个切块</ElTag>
      </div>

      <div class="toolbar-right">
        <ElButton circle :loading="loading" @click="refreshData">
          <el-icon><Refresh /></el-icon>
        </ElButton>
      </div>
    </div>

    <!-- 缺少 docId 提示 -->
    <ElAlert
      v-if="!docId"
      title="缺少文档参数"
      description="请从「文档管理」页点击某文档的「块」按钮进入，URL 需携带 docId 参数。"
      type="warning"
      :closable="false"
      show-icon
      style="margin-bottom: 12px"
    />

    <ArtTable
      :columns="columns"
      :data="data"
      :loading="loading"
      :pagination="pagination"
      :paginationOptions="{ pageSizes: [20, 50, 100], hideOnSinglePage: false }"
      empty-height="420"
      emptyText="暂无切块"
      @pagination:size-change="handleSizeChange"
      @pagination:current-change="handleCurrentChange"
    >
      <template #chunk_index="{ row }">
        <span class="mono">#{{ row.chunk_index }}</span>
      </template>
      <template #content="{ row }">
        <div class="chunk-content" :title="row.content">{{ row.content }}</div>
      </template>
      <template #page_number="{ row }">
        <span v-if="row.page_number != null">第 {{ row.page_number }} 页</span>
        <span v-else class="muted">-</span>
      </template>
      <template #vectorized="{ row }">
        <ElTag size="small" :type="row.vectorized ? 'success' : 'warning'" effect="plain">
          {{ row.vectorized ? '已向量化' : '未向量化' }}
        </ElTag>
      </template>
      <template #actions="{ row }">
        <ElButton link type="primary" @click="openChunk(row)">查看</ElButton>
      </template>
    </ArtTable>

    <!-- 切块详情抽屉 -->
    <ElDrawer v-model="detailVisible" title="切块详情" size="50%">
      <template v-if="currentChunk">
        <ElDescriptions :column="2" border size="small" style="margin-bottom: 16px">
          <ElDescriptionsItem label="切块 ID">{{ currentChunk.id }}</ElDescriptionsItem>
          <ElDescriptionsItem label="序号">#{{ currentChunk.chunk_index }}</ElDescriptionsItem>
          <ElDescriptionsItem label="页码">
            {{ currentChunk.page_number != null ? `第 ${currentChunk.page_number} 页` : '-' }}
          </ElDescriptionsItem>
          <ElDescriptionsItem label="Token 数">{{ currentChunk.token_count }}</ElDescriptionsItem>
          <ElDescriptionsItem label="向量化">
            <ElTag
              size="small"
              :type="currentChunk.vectorized ? 'success' : 'warning'"
              effect="plain"
            >
              {{ currentChunk.vectorized ? '已向量化' : '未向量化' }}
            </ElTag>
          </ElDescriptionsItem>
        </ElDescriptions>
        <div class="detail-title">正文</div>
        <div class="detail-content">{{ currentChunk.content }}</div>
      </template>
    </ElDrawer>
  </div>
</template>

<script setup lang="ts">
  import { Back, Refresh } from '@element-plus/icons-vue'
  import { fetchChunkPage } from '@/api/everkb/chunk'
  import { fetchDocumentDetail } from '@/api/document'
  import type { ColumnOption } from '@/types/component'
  import { useTable } from '@/hooks/core/useTable'

  defineOptions({ name: 'EverKBChunk' })

  type ChunkRow = Api.EverKB.Chunk

  const route = useRoute()
  const router = useRouter()

  const docId = computed(() => Number(route.query.docId) || 0)
  const docName = ref('')
  const total = ref(0)

  // ── 表格 ─────────────────────────────────────────────────────────
  const apiFn = (params: Record<string, unknown>) => fetchChunkPage(docId.value, params)

  const {
    data,
    loading,
    columns,
    pagination,
    fetchData,
    refreshData,
    handleSizeChange,
    handleCurrentChange
  } = useTable({
    core: {
      apiFn,
      apiParams: { page: 1, size: 20 },
      paginationKey: { current: 'page' },
      immediate: false,
      columnsFactory: (): ColumnOption<ChunkRow>[] => [
        { prop: 'id', label: 'ID', width: 90 },
        { prop: 'chunk_index', label: '序号', width: 90, useSlot: true },
        { prop: 'content', label: '正文', minWidth: 360, useSlot: true },
        { prop: 'page_number', label: '页码', width: 110, useSlot: true },
        { prop: 'token_count', label: 'Token', width: 90 },
        { prop: 'vectorized', label: '向量化', width: 110, useSlot: true },
        { prop: 'actions', label: '操作', width: 80, fixed: 'right', useSlot: true }
      ]
    },
    performance: { enableCache: false }
  })

  // ── 加载文档名（用于工具条展示）──────────────────────────────────
  const loadDocName = async () => {
    if (!docId.value) return
    try {
      const doc = await fetchDocumentDetail(docId.value)
      docName.value = doc.name
    } catch {
      // 文档不存在时 http 层已弹错误，标题回退为 #id
    }
  }

  onMounted(async () => {
    if (!docId.value) return
    await loadDocName()
    void fetchData()
  })

  // ── 返回文档页 ───────────────────────────────────────────────────
  const goBack = () => {
    router.push('/everkb/document')
  }

  // ── 切块详情 ─────────────────────────────────────────────────────
  const detailVisible = ref(false)
  const currentChunk = ref<ChunkRow | null>(null)

  const openChunk = (row: ChunkRow) => {
    currentChunk.value = row
    detailVisible.value = true
  }
</script>

<style lang="scss" scoped>
  .chunk-page {
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

      .toolbar-label {
        font-size: 13px;
        color: var(--art-gray-600, #888);
      }

      .toolbar-divider {
        width: 1px;
        height: 14px;
        background: var(--art-border-color-light, #ebeef5);
      }

      .doc-title {
        font-weight: 600;
        font-size: 14px;
      }
    }
  }

  .mono {
    font-family: ui-monospace, 'SF Mono', Menlo, Consolas, monospace;
    font-size: 12px;
  }

  .chunk-content {
    display: -webkit-box;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 2;
    overflow: hidden;
    line-height: 1.6;
    font-size: 13px;
    word-break: break-word;
  }

  .muted {
    color: var(--art-gray-600, #888);
  }

  .detail-title {
    font-size: 14px;
    font-weight: 600;
    margin-bottom: 8px;
  }

  .detail-content {
    padding: 12px;
    background: var(--art-fill-color-light, #f5f7fa);
    border-radius: 6px;
    font-size: 13px;
    line-height: 1.7;
    white-space: pre-wrap;
    word-break: break-word;
    max-height: 60vh;
    overflow-y: auto;
  }
</style>
