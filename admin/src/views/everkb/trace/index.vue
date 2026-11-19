<template>
  <div class="trace-page">
    <ElTabs v-model="activeTab" class="trace-tabs">
      <!-- Tab 1: Trace 列表（复用 records，点开进详情） -->
      <ElTabPane :label="$t('everkb.trace.tabList')" name="list">
        <ArtTable
          :columns="columns"
          :data="data"
          :loading="loading"
          :pagination="pagination"
          :paginationOptions="{ pageSizes: [20, 50, 100], hideOnSinglePage: false }"
          empty-height="420"
          :emptyText="$t('everkb.trace.emptyQaRecords')"
          @pagination:size-change="handleSizeChange"
          @pagination:current-change="handleCurrentChange"
        >
          <template #question="{ row }">
            <span class="cell-ellipsis" :title="row.question">{{ row.question }}</span>
          </template>
          <template #actions="{ row }">
            <ElButton link type="primary" @click="openDetail(row)">{{
              $t('everkb.trace.viewTrace')
            }}</ElButton>
          </template>
        </ArtTable>
      </ElTabPane>

      <!-- Tab 2: 聚合分析 -->
      <ElTabPane :label="$t('everkb.trace.tabAggregate')" name="aggregate">
        <div
          v-if="aggLoading"
          v-loading="true"
          :element-loading-text="$t('everkb.trace.loading')"
          class="agg-loading"
        />
        <template v-else-if="aggregation">
          <div class="agg-section">
            <div class="agg-section-title">{{
              $t('everkb.trace.slowestTop', { n: aggregation.slowest?.length ?? 0 })
            }}</div>
            <ElTable :data="aggregation.slowest" size="small" border>
              <ElTableColumn prop="trace_id" label="Trace" width="90" />
              <ElTableColumn prop="name" :label="$t('everkb.trace.spanName')" min-width="180" />
              <ElTableColumn :label="$t('everkb.trace.type')" width="100">
                <template #default="{ row }">{{ spanTypeLabel(row.span_type) }}</template>
              </ElTableColumn>
              <ElTableColumn
                :label="$t('everkb.trace.latency')"
                width="110"
                sortable
                :sort-method="(a, b) => a.latency_ms - b.latency_ms"
              >
                <template #default="{ row }">
                  <span :class="{ 'slow-text': row.latency_ms >= 1000 }"
                    >{{ row.latency_ms }}ms</span
                  >
                </template>
              </ElTableColumn>
              <ElTableColumn :label="$t('everkb.trace.tokensInOut')" width="130">
                <template #default="{ row }">
                  {{ row.gen_ai_usage_tokens_in ?? '-' }} / {{ row.gen_ai_usage_tokens_out ?? '-' }}
                </template>
              </ElTableColumn>
              <ElTableColumn :label="$t('everkb.trace.cost')" width="110">
                <template #default="{ row }">{{
                  row.cost == null ? '-' : `¥${row.cost.toFixed(6)}`
                }}</template>
              </ElTableColumn>
              <ElTableColumn :label="$t('everkb.trace.time')" width="170">
                <template #default="{ row }">{{ formatTime(row.start_time) }}</template>
              </ElTableColumn>
            </ElTable>
          </div>

          <div class="agg-section">
            <div class="agg-section-title">{{ $t('everkb.trace.typeMetrics') }}</div>
            <ElTable :data="aggregation.by_type" size="small" border>
              <ElTableColumn :label="$t('everkb.trace.type')" width="140">
                <template #default="{ row }">{{ spanTypeLabel(row.span_type) }}</template>
              </ElTableColumn>
              <ElTableColumn prop="count" :label="$t('everkb.trace.count')" width="90" />
              <ElTableColumn :label="$t('everkb.trace.p95Latency')" width="120">
                <template #default="{ row }">{{ row.p95_latency_ms ?? '-' }}ms</template>
              </ElTableColumn>
              <ElTableColumn :label="$t('everkb.trace.avgTokensIn')" width="130">
                <template #default="{ row }">{{ row.avg_tokens_in ?? '-' }}</template>
              </ElTableColumn>
              <ElTableColumn :label="$t('everkb.trace.avgTokensOut')" width="130">
                <template #default="{ row }">{{ row.avg_tokens_out ?? '-' }}</template>
              </ElTableColumn>
              <ElTableColumn :label="$t('everkb.trace.avgCost')" width="130">
                <template #default="{ row }">{{
                  row.avg_cost == null ? '-' : `¥${row.avg_cost.toFixed(6)}`
                }}</template>
              </ElTableColumn>
            </ElTable>
          </div>
        </template>
      </ElTabPane>

      <!-- Tab 3: 入库链路（二期 Task 29：文档解析管线 span） -->
      <ElTabPane :label="$t('everkb.trace.tabPipeline')" name="pipeline">
        <ArtTable
          :columns="pipelineColumns"
          :data="pipelineData"
          :loading="pipelineLoading"
          :pagination="pipelinePagination"
          :paginationOptions="{ pageSizes: [20, 50, 100], hideOnSinglePage: false }"
          empty-height="420"
          :emptyText="$t('everkb.trace.emptyPipeline')"
          @pagination:size-change="handlePipelineSizeChange"
          @pagination:current-change="handlePipelineCurrentChange"
        >
          <template #trace_id="{ row }">
            <span class="cell-ellipsis" :title="`Trace #${row.trace_id}`">{{ row.trace_id }}</span>
          </template>
          <template #doc_name="{ row }">
            <ElButton link type="primary" @click="openPipelineDetail(row)">
              {{ row.doc_name ?? $t('everkb.trace.docFallback', { id: row.doc_id }) }}
            </ElButton>
          </template>
          <template #doc_status="{ row }">{{ docStatusLabel(row.doc_status) }}</template>
          <template #span_count="{ row }">{{ row.span_count }}</template>
          <template #total_latency_ms="{ row }">{{ row.total_latency_ms }}ms</template>
          <template #last_start_time="{ row }">{{ formatTime(row.last_start_time) }}</template>
          <template #actions="{ row }">
            <ElButton link type="primary" @click="openPipelineDetail(row)">{{
              $t('everkb.trace.viewSpanTree')
            }}</ElButton>
          </template>
        </ArtTable>
      </ElTabPane>
    </ElTabs>
  </div>
</template>

<script setup lang="ts">
  import { useI18n } from 'vue-i18n'
  import { useRouter } from 'vue-router'
  import { fetchQaRecordPage } from '@/api/everkb/qa-record'
  import { fetchPipelineTraces, fetchTraceAggregation } from '@/api/everkb/trace'
  import type { ColumnOption } from '@/types/component'
  import { useTable } from '@/hooks/core/useTable'

  defineOptions({ name: 'EverKBTrace' })

  type QaRow = Api.EverKB.QaRecord
  type PipelineRow = Api.EverKB.PipelineTraceItem

  const { t } = useI18n()
  const router = useRouter()
  const activeTab = ref('list')

  // ── Tab 1: Trace 列表（复用 records）─────────────────────────────
  const apiFn = (params: Record<string, unknown>) => fetchQaRecordPage(params)

  const { data, loading, columns, pagination, fetchData, handleSizeChange, handleCurrentChange } =
    useTable({
      core: {
        apiFn,
        apiParams: { page: 1, size: 20 },
        paginationKey: { current: 'page' },
        immediate: true,
        columnsFactory: (): ColumnOption<QaRow>[] => [
          { prop: 'id', label: 'ID', width: 80 },
          { prop: 'question', label: t('everkb.trace.question'), minWidth: 240, useSlot: true },
          { prop: 'app_id', label: t('everkb.trace.app'), width: 90 },
          {
            prop: 'grounded',
            label: t('everkb.trace.grounded'),
            width: 110,
            formatter: (row) =>
              row.grounded ? t('everkb.trace.groundedYes') : t('everkb.trace.groundedNo')
          },
          {
            prop: 'latency_ms',
            label: t('everkb.trace.latency'),
            width: 100,
            formatter: (row) => `${row.latency_ms}ms`
          },
          {
            prop: 'created_at',
            label: t('everkb.trace.time'),
            width: 170,
            formatter: (row) => row.created_at?.replace('T', ' ').slice(0, 19) || '-'
          },
          {
            prop: 'actions',
            label: t('everkb.trace.actions'),
            width: 110,
            fixed: 'right',
            useSlot: true
          }
        ]
      },
      performance: { enableCache: false }
    })

  const openDetail = (row: QaRow) => {
    router.push({ path: '/everkb/trace-detail', query: { traceId: String(row.id) } })
  }

  // ── Tab 2: 聚合分析 ──────────────────────────────────────────────
  const aggLoading = ref(false)
  const aggregation = ref<Api.EverKB.TraceAggregation | null>(null)

  const loadAggregation = async () => {
    aggLoading.value = true
    try {
      aggregation.value = await fetchTraceAggregation()
    } catch {
      // http 层已弹错误
    } finally {
      aggLoading.value = false
    }
  }

  const spanTypeLabel = (type: string) => {
    const labels: Record<string, string> = {
      embedding: t('everkb.trace.spanTypeEmbedding'),
      retrieval: t('everkb.trace.spanTypeRetrieval'),
      db: t('everkb.trace.spanTypeDatabase'),
      llm: 'LLM',
      tool: t('everkb.trace.spanTypeTool'),
      agent_step: t('everkb.trace.spanTypeOrchestration'),
      parse: t('everkb.trace.spanTypeParse'),
      chunking: t('everkb.trace.spanTypeChunking'),
      vector_insert: t('everkb.trace.spanTypeVectorInsert')
    }
    return labels[type] ?? type
  }

  const formatTime = (iso: string) => iso?.replace('T', ' ').slice(0, 19) || '-'

  // ── Tab 3: 入库链路（管线 Trace）─────────────────────────────
  const docStatusLabel = (s: number | null) => {
    if (s == null) return '-'
    const labels: Record<number, string> = {
      1: t('everkb.trace.docStatusUploaded'),
      2: t('everkb.trace.docStatusParsing'),
      3: t('everkb.trace.docStatusExtracted'),
      4: t('everkb.trace.docStatusChunked'),
      5: t('everkb.trace.docStatusVectorizing'),
      6: t('everkb.trace.docStatusCompleted'),
      7: t('everkb.trace.docStatusFailed')
    }
    return labels[s] ?? t('everkb.trace.docStatusUnknown', { n: s })
  }

  const pipelineApiFn = (params: Record<string, unknown>) => fetchPipelineTraces(params)

  const {
    data: pipelineData,
    loading: pipelineLoading,
    columns: pipelineColumns,
    pagination: pipelinePagination,
    fetchData: fetchPipeline,
    handleSizeChange: handlePipelineSizeChange,
    handleCurrentChange: handlePipelineCurrentChange
  } = useTable({
    core: {
      apiFn: pipelineApiFn,
      apiParams: { page: 1, size: 20 },
      paginationKey: { current: 'page' },
      immediate: false,
      columnsFactory: (): ColumnOption<PipelineRow>[] => [
        { prop: 'trace_id', label: 'Trace ID', width: 100, useSlot: true },
        { prop: 'doc_name', label: t('everkb.trace.doc'), minWidth: 200, useSlot: true },
        { prop: 'doc_status', label: t('everkb.trace.status'), width: 100, useSlot: true },
        { prop: 'span_count', label: t('everkb.trace.spanCount'), width: 90, useSlot: true },
        {
          prop: 'total_latency_ms',
          label: t('everkb.trace.totalLatency'),
          width: 110,
          useSlot: true
        },
        { prop: 'last_start_time', label: t('everkb.trace.lastTime'), width: 170, useSlot: true },
        {
          prop: 'actions',
          label: t('everkb.trace.actions'),
          width: 120,
          fixed: 'right',
          useSlot: true
        }
      ]
    },
    performance: { enableCache: false }
  })

  const openPipelineDetail = (row: PipelineRow) => {
    router.push({ path: '/everkb/trace-detail', query: { traceId: String(row.trace_id) } })
  }

  // 切换到聚合/入库链路 tab 时才加载
  watch(activeTab, (tab) => {
    if (tab === 'aggregate' && !aggregation.value) void loadAggregation()
    if (tab === 'pipeline') void fetchPipeline()
  })

  onMounted(() => {
    void fetchData()
  })
</script>

<style lang="scss" scoped>
  .trace-page {
    padding: 16px;

    .trace-tabs {
      :deep(.el-tabs__header) {
        margin-bottom: 16px;
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

    .agg-loading {
      min-height: 300px;
    }

    .agg-section {
      margin-bottom: 24px;

      .agg-section-title {
        font-size: 14px;
        font-weight: 600;
        margin-bottom: 10px;
      }
    }

    .slow-text {
      color: var(--el-color-danger, #f56c6c);
      font-weight: 600;
    }
  }
</style>
