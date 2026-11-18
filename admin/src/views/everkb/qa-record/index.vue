<template>
  <div class="qa-page">
    <!-- 工具条：应用筛选 + 反馈筛选 + 刷新 -->
    <div class="toolbar art-card-sm">
      <div class="toolbar-left">
        <span class="toolbar-label">应用</span>
        <ElSelect
          v-model="appFilter"
          :loading="appLoading"
          placeholder="全部应用"
          clearable
          filterable
          style="width: 200px"
          @change="handleFilterChange"
        >
          <ElOption v-for="app in appList" :key="app.id" :label="app.name" :value="app.id" />
        </ElSelect>

        <span class="toolbar-label">反馈</span>
        <ElSelect
          v-model="feedbackFilter"
          placeholder="全部"
          clearable
          style="width: 140px"
          @change="handleFilterChange"
        >
          <ElOption :label="FEEDBACK_META[FEEDBACK.Good].label" :value="FEEDBACK.Good" />
          <ElOption :label="FEEDBACK_META[FEEDBACK.Bad].label" :value="FEEDBACK.Bad" />
          <ElOption :label="FEEDBACK_META[FEEDBACK.None].label" :value="FEEDBACK.None" />
        </ElSelect>
      </div>

      <div class="toolbar-right">
        <ElButton circle @click="refreshData">
          <el-icon><Refresh /></el-icon>
        </ElButton>
      </div>
    </div>

    <ArtTable
      :columns="columns"
      :data="data"
      :loading="loading"
      :pagination="pagination"
      :paginationOptions="{ pageSizes: [20, 50, 100], hideOnSinglePage: false }"
      empty-height="420"
      emptyText="暂无问答记录"
      @pagination:size-change="handleSizeChange"
      @pagination:current-change="handleCurrentChange"
    >
      <template #app_id="{ row }">
        <span>{{ appNameMap[row.app_id] ?? `#${row.app_id}` }}</span>
      </template>
      <template #question="{ row }">
        <span class="cell-ellipsis" :title="row.question">{{ row.question }}</span>
      </template>
      <template #answer="{ row }">
        <span class="cell-ellipsis muted" :title="row.answer">{{ row.answer }}</span>
      </template>
      <template #grounded="{ row }">
        <ElTag size="small" :type="row.grounded ? 'success' : 'warning'" effect="plain">
          {{ row.grounded ? '已基于知识库' : '自由回答' }}
        </ElTag>
      </template>
      <template #citations="{ row }">
        <span>{{ row.citations?.length ?? 0 }}</span>
      </template>
      <template #feedback="{ row }">
        <ElTag size="small" :type="FEEDBACK_META[row.feedback]?.tag || 'info'" effect="plain">
          {{ FEEDBACK_META[row.feedback]?.label ?? `未知(${row.feedback})` }}
        </ElTag>
      </template>
      <template #actions="{ row }">
        <ElButton link type="primary" @click="openDetail(row)">详情</ElButton>
      </template>
    </ArtTable>

    <!-- 详情抽屉 -->
    <ElDrawer v-model="detailVisible" title="问答记录详情" size="56%">
      <div
        v-if="detailLoading"
        v-loading="true"
        element-loading-text="加载中"
        class="detail-loading"
      />
      <template v-else-if="detail">
        <div class="detail-section">
          <div class="detail-section-title">问题</div>
          <div class="detail-block">{{ detail.question }}</div>
        </div>
        <div class="detail-section">
          <div class="detail-section-title">回答</div>
          <div class="detail-block answer-block">{{ detail.answer }}</div>
        </div>
        <div class="detail-section">
          <div class="detail-section-title">引用（{{ detail.citations?.length ?? 0 }}）</div>
          <ElEmpty
            v-if="!detail.citations?.length"
            description="无引用（自由回答）"
            :image-size="60"
          />
          <div v-else class="citation-list">
            <div v-for="(c, i) in detail.citations" :key="i" class="citation-item">
              <div class="citation-head">
                <span class="citation-index">[{{ i + 1 }}]</span>
                <span class="citation-name">{{ c.doc_name }}</span>
                <ElTag v-if="c.page_number != null" size="small" type="info" effect="plain">
                  第 {{ c.page_number }} 页
                </ElTag>
                <ElTag size="small" type="primary" effect="plain"
                  >score {{ c.score?.toFixed(3) }}</ElTag
                >
              </div>
              <div class="citation-snippet">{{ c.snippet }}</div>
            </div>
          </div>
        </div>
        <div class="detail-section">
          <div class="detail-section-title">元信息</div>
          <ElDescriptions :column="2" border size="small">
            <ElDescriptionsItem label="记录 ID">{{ detail.id }}</ElDescriptionsItem>
            <ElDescriptionsItem label="应用">
              {{ appNameMap[detail.app_id] ?? `#${detail.app_id}` }}
            </ElDescriptionsItem>
            <ElDescriptionsItem label="反馈">
              {{ FEEDBACK_META[detail.feedback]?.label ?? `未知(${detail.feedback})` }}
            </ElDescriptionsItem>
            <ElDescriptionsItem label="grounded">{{
              detail.grounded ? '是' : '否'
            }}</ElDescriptionsItem>
            <ElDescriptionsItem label="耗时">{{ detail.latency_ms }} ms</ElDescriptionsItem>
            <ElDescriptionsItem label="总花费">
              {{ detail.total_cost == null ? '-' : `¥${detail.total_cost.toFixed(6)}` }}
            </ElDescriptionsItem>
            <ElDescriptionsItem label="user_key">{{ detail.user_key || '-' }}</ElDescriptionsItem>
            <ElDescriptionsItem label="创建时间">
              {{ detail.created_at?.replace('T', ' ').slice(0, 19) }}
            </ElDescriptionsItem>
            <ElDescriptionsItem label="模型快照" :span="2">
              <code class="mono">{{ JSON.stringify(detail.model_snapshot ?? {}) }}</code>
            </ElDescriptionsItem>
          </ElDescriptions>
        </div>
      </template>
    </ElDrawer>
  </div>
</template>

<script setup lang="ts">
  import { ElMessage } from 'element-plus'
  import { Refresh } from '@element-plus/icons-vue'
  import { fetchQaRecordDetail, fetchQaRecordPage } from '@/api/everkb/qa-record'
  import { fetchAppList } from '@/api/everkb/app'
  import { FEEDBACK } from '@/constants/everkb'
  import type { ColumnOption } from '@/types/component'
  import { useTable } from '@/hooks/core/useTable'

  defineOptions({ name: 'EverKBQaRecord' })

  type QaRow = Api.EverKB.QaRecord

  const FEEDBACK_META: Record<
    number,
    { label: string; tag: 'info' | 'success' | 'danger' | 'warning' }
  > = {
    [FEEDBACK.None]: { label: '未反馈', tag: 'info' },
    [FEEDBACK.Good]: { label: '满意', tag: 'success' },
    [FEEDBACK.Bad]: { label: '不满意', tag: 'danger' }
  }

  // ── 应用下拉（筛选）─────────────────────────────────────────────
  const appList = ref<Api.EverKB.App[]>([])
  const appLoading = ref(false)
  const appNameMap = computed<Record<number, string>>(() => {
    const map: Record<number, string> = {}
    for (const app of appList.value) map[app.id] = app.name
    return map
  })

  const loadApps = async () => {
    appLoading.value = true
    try {
      appList.value = await fetchAppList()
    } catch {
      // 错误已由 http 层弹出
    } finally {
      appLoading.value = false
    }
  }

  // ── 表格 ─────────────────────────────────────────────────────────
  const apiFn = (params: Record<string, unknown>) => fetchQaRecordPage(params)

  const {
    data,
    loading,
    columns,
    pagination,
    fetchData,
    refreshData,
    searchParams,
    handleSizeChange,
    handleCurrentChange
  } = useTable({
    core: {
      apiFn,
      apiParams: { page: 1, size: 20 },
      paginationKey: { current: 'page' },
      immediate: true,
      columnsFactory: (): ColumnOption<QaRow>[] => [
        { prop: 'id', label: 'ID', width: 80 },
        { prop: 'app_id', label: '应用', width: 150, useSlot: true },
        { prop: 'question', label: '问题', minWidth: 200, useSlot: true },
        { prop: 'answer', label: '回答', minWidth: 220, useSlot: true },
        { prop: 'grounded', label: '依据', width: 130, useSlot: true },
        { prop: 'citations', label: '引用数', width: 80, useSlot: true },
        { prop: 'feedback', label: '反馈', width: 100, useSlot: true },
        {
          prop: 'created_at',
          label: '时间',
          width: 170,
          formatter: (row) => row.created_at?.replace('T', ' ').slice(0, 19) || '-'
        },
        { prop: 'actions', label: '操作', width: 80, fixed: 'right', useSlot: true }
      ]
    },
    performance: { enableCache: false }
  })

  const appFilter = ref<number | undefined>(undefined)
  const feedbackFilter = ref<number | undefined>(undefined)

  const handleFilterChange = () => {
    searchParams.app_id = appFilter.value
    searchParams.feedback = feedbackFilter.value
    searchParams.page = 1
    void fetchData()
  }

  // ── 详情抽屉 ─────────────────────────────────────────────────────
  const detailVisible = ref(false)
  const detailLoading = ref(false)
  const detail = ref<QaRow | null>(null)

  const openDetail = async (row: QaRow) => {
    detailVisible.value = true
    detailLoading.value = true
    detail.value = null
    try {
      detail.value = await fetchQaRecordDetail(row.id)
    } catch {
      detailVisible.value = false
      ElMessage.error('加载详情失败')
    } finally {
      detailLoading.value = false
    }
  }

  onMounted(() => {
    void loadApps()
  })
</script>

<style lang="scss" scoped>
  .qa-page {
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
    }
  }

  .cell-ellipsis {
    display: inline-block;
    max-width: 100%;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    vertical-align: middle;
  }

  .muted {
    color: var(--art-gray-600, #888);
  }

  .mono {
    font-family: ui-monospace, 'SF Mono', Menlo, Consolas, monospace;
    font-size: 12px;
    word-break: break-all;
  }

  .detail-loading {
    min-height: 200px;
  }

  .detail-section {
    margin-bottom: 20px;

    .detail-section-title {
      font-size: 14px;
      font-weight: 600;
      margin-bottom: 8px;
    }

    .detail-block {
      padding: 10px 12px;
      background: var(--art-fill-color-light, #f5f7fa);
      border-radius: 6px;
      font-size: 13px;
      line-height: 1.7;
      white-space: pre-wrap;
      word-break: break-word;
    }

    .answer-block {
      max-height: 320px;
      overflow-y: auto;
    }
  }

  .citation-list {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  .citation-item {
    padding: 10px 12px;
    border: 1px solid var(--art-border-color-light, #ebeef5);
    border-radius: 6px;

    .citation-head {
      display: flex;
      align-items: center;
      gap: 8px;
      margin-bottom: 6px;
    }

    .citation-index {
      color: var(--art-color-primary, #409eff);
      font-weight: 600;
    }

    .citation-name {
      font-weight: 600;
      font-size: 13px;
    }

    .citation-snippet {
      font-size: 12px;
      color: var(--art-gray-600, #888);
      line-height: 1.6;
      word-break: break-word;
    }
  }
</style>
