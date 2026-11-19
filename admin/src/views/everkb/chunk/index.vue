<template>
  <div class="chunk-page">
    <!-- 工具条：文档信息 + 返回 -->
    <div class="toolbar art-card-sm">
      <div class="toolbar-left">
        <ElButton link type="primary" @click="goBack">
          <el-icon style="margin-right: 4px"><Back /></el-icon>
          {{ $t('everkb.chunk.backToDoc') }}
        </ElButton>
        <span class="toolbar-divider" />
        <span class="toolbar-label">{{ $t('everkb.chunk.docLabel') }}</span>
        <span class="doc-title">{{ docName || `#${docId}` }}</span>
        <ElTag v-if="total > 0" size="small" effect="plain">{{
          $t('everkb.chunk.totalCount', { n: total })
        }}</ElTag>
      </div>

      <div class="toolbar-right">
        <ElButton circle :loading="loading" @click="refreshData">
          <el-icon><Refresh /></el-icon>
        </ElButton>
      </div>
    </div>

    <!-- 无 docId：文档选择器（知识库 → 文档 两级联动） -->
    <div v-if="!docId" class="picker-card art-card-sm">
      <div class="picker-title">{{ $t('everkb.chunk.pickDocTitle') }}</div>
      <div class="picker-row">
        <ElSelect
          v-model="pickerKbId"
          :loading="kbLoading"
          :placeholder="$t('everkb.document.selectKnowledgeBase')"
          style="width: 240px"
          @change="handlePickerKbChange"
        >
          <ElOption v-for="kb in kbList" :key="kb.id" :label="kb.name" :value="kb.id" />
        </ElSelect>
        <ElSelect
          v-model="pickerDocId"
          :loading="docLoading"
          :placeholder="$t('everkb.chunk.pickDocPlaceholder')"
          :disabled="!pickerKbId"
          filterable
          style="width: 320px"
          @change="handlePickerDocChange"
        >
          <ElOption v-for="d in pickerDocList" :key="d.id" :label="d.name" :value="d.id" />
        </ElSelect>
      </div>
    </div>

    <ArtTable
      :columns="columns"
      :data="data"
      :loading="loading"
      :pagination="pagination"
      :paginationOptions="{ pageSizes: [20, 50, 100], hideOnSinglePage: false }"
      empty-height="420"
      :emptyText="$t('everkb.chunk.emptyText')"
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
        <span v-if="row.page_number != null">{{
          $t('everkb.chunk.pageNumber', { n: row.page_number })
        }}</span>
        <span v-else class="muted">-</span>
      </template>
      <template #vectorized="{ row }">
        <ElTag size="small" :type="row.vectorized ? 'success' : 'warning'" effect="plain">
          {{ row.vectorized ? $t('everkb.chunk.vectorized') : $t('everkb.chunk.notVectorized') }}
        </ElTag>
      </template>
      <template #actions="{ row }">
        <ElButton link type="primary" @click="openChunk(row)">{{
          $t('everkb.chunk.view')
        }}</ElButton>
      </template>
    </ArtTable>

    <!-- 切块详情抽屉 -->
    <ElDrawer v-model="detailVisible" :title="$t('everkb.chunk.detailTitle')" size="50%">
      <template v-if="currentChunk">
        <ElDescriptions :column="2" border size="small" style="margin-bottom: 16px">
          <ElDescriptionsItem :label="$t('everkb.chunk.chunkId')">{{
            currentChunk.id
          }}</ElDescriptionsItem>
          <ElDescriptionsItem :label="$t('everkb.chunk.indexLabel')"
            >#{{ currentChunk.chunk_index }}</ElDescriptionsItem
          >
          <ElDescriptionsItem :label="$t('everkb.chunk.pageLabel')">
            {{
              currentChunk.page_number != null
                ? $t('everkb.chunk.pageNumber', { n: currentChunk.page_number })
                : '-'
            }}
          </ElDescriptionsItem>
          <ElDescriptionsItem :label="$t('everkb.chunk.tokenCount')">{{
            currentChunk.token_count
          }}</ElDescriptionsItem>
          <ElDescriptionsItem :label="$t('everkb.chunk.vectorizedLabel')">
            <ElTag
              size="small"
              :type="currentChunk.vectorized ? 'success' : 'warning'"
              effect="plain"
            >
              {{
                currentChunk.vectorized
                  ? $t('everkb.chunk.vectorized')
                  : $t('everkb.chunk.notVectorized')
              }}
            </ElTag>
          </ElDescriptionsItem>
        </ElDescriptions>
        <div class="detail-title">{{ $t('everkb.chunk.contentLabel') }}</div>
        <div class="detail-content">{{ currentChunk.content }}</div>
      </template>
    </ElDrawer>
  </div>
</template>

<script setup lang="ts">
  import { Back, Refresh } from '@element-plus/icons-vue'
  import { useI18n } from 'vue-i18n'
  import { fetchChunkPage } from '@/api/everkb/chunk'
  import { fetchDocumentDetail, fetchDocumentPage } from '@/api/document'
  import { fetchKbList } from '@/api/kb'
  import type { ColumnOption } from '@/types/component'
  import { useTable } from '@/hooks/core/useTable'

  defineOptions({ name: 'EverKBChunk' })

  const { t } = useI18n()

  type ChunkRow = Api.EverKB.Chunk

  const route = useRoute()
  const router = useRouter()

  const docId = computed(() => Number(route.query.docId) || 0)
  const docName = ref('')
  const total = ref(0)

  // ── 无 docId 时的文档选择器（知识库 → 文档 两级联动）──────────────
  const kbList = ref<Api.EverKB.KB[]>([])
  const kbLoading = ref(false)
  const pickerKbId = ref<number | null>(null)
  const pickerDocList = ref<Api.EverKB.Document[]>([])
  const docLoading = ref(false)
  const pickerDocId = ref<number | null>(null)

  const loadKbList = async () => {
    kbLoading.value = true
    try {
      kbList.value = await fetchKbList()
      if (!pickerKbId.value && kbList.value.length) {
        pickerKbId.value = kbList.value[0].id
        void loadDocList()
      }
    } catch {
      // 错误已由 http 层弹出
    } finally {
      kbLoading.value = false
    }
  }

  const loadDocList = async () => {
    if (!pickerKbId.value) {
      pickerDocList.value = []
      pickerDocId.value = null
      return
    }
    docLoading.value = true
    try {
      const page = await fetchDocumentPage(pickerKbId.value, { page: 1, size: 100 })
      pickerDocList.value = page.items
      pickerDocId.value = null
    } catch {
      // 错误已由 http 层弹出
    } finally {
      docLoading.value = false
    }
  }

  const handlePickerKbChange = () => {
    void loadDocList()
  }

  const handlePickerDocChange = (val: number) => {
    if (!val) return
    // 选中文档后，把 docId 写入 URL，复用后续 docId 驱动的加载逻辑
    router.replace({ path: '/everkb/chunk', query: { docId: String(val) } })
  }

  // ── 表格 ─────────────────────────────────────────────────────────
  const apiFn = (params: Record<string, unknown>) => fetchChunkPage(docId.value, params)

  const {
    data,
    loading,
    columns,
    pagination,
    fetchData,
    getData,
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
        { prop: 'chunk_index', label: t('everkb.chunk.indexLabel'), width: 90, useSlot: true },
        { prop: 'content', label: t('everkb.chunk.contentLabel'), minWidth: 360, useSlot: true },
        { prop: 'page_number', label: t('everkb.chunk.pageLabel'), width: 110, useSlot: true },
        { prop: 'token_count', label: 'Token', width: 90 },
        { prop: 'vectorized', label: t('everkb.chunk.vectorizedLabel'), width: 110, useSlot: true },
        {
          prop: 'actions',
          label: t('everkb.chunk.actions'),
          width: 80,
          fixed: 'right',
          useSlot: true
        }
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
    if (!docId.value) {
      // 无 docId：展示文档选择器，让管理员选择要浏览切块的文档
      void loadKbList()
      return
    }
    await loadDocName()
    void fetchData()
  })

  // ── docId 变化时重新加载（keepAlive 缓存下，选择器改 query 不会重挂载）──
  watch(docId, async (val, old) => {
    if (val === old) return
    if (!val) {
      // 清掉 docId（如用户手动清 query）：回到选择器
      docName.value = ''
      total.value = 0
      data.value = []
      void loadKbList()
      return
    }
    await loadDocName()
    void getData()
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

    .picker-card {
      padding: 20px 16px;
      margin-bottom: 12px;

      .picker-title {
        font-size: 14px;
        font-weight: 600;
        margin-bottom: 12px;
      }

      .picker-row {
        display: flex;
        align-items: center;
        flex-wrap: wrap;
        gap: 12px;
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
