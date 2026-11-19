<template>
  <div class="dashboard-page">
    <!-- 顶部 KPI 统计卡片（可点击下钻） -->
    <div class="stats-grid">
      <div
        v-for="card in statCards"
        :key="card.label"
        class="stat-card-link"
        :class="{ 'has-alert': card.alert }"
        @click="goTo(card.path)"
      >
        <ArtStatsCard
          :title="card.label"
          :count="card.value"
          :description="card.description"
          :icon="card.icon"
          :icon-style="card.iconStyle"
          :decimals="card.decimals"
          show-arrow
        />
        <ElBadge v-if="card.alert" :value="card.alert" class="stat-badge" type="danger" />
      </div>
    </div>

    <!-- 中区：趋势图 + 分布图 -->
    <div class="chart-row">
      <div class="chart-panel art-card-sm">
        <div class="panel-title">问答活跃趋势（近 14 天）</div>
        <div ref="trendChartRef" class="chart-canvas" v-loading="loading" />
      </div>

      <div class="chart-panel art-card-sm">
        <div class="panel-title">检索模式分布</div>
        <ArtRingChart
          :data="retrievalModeData"
          :show-legend="true"
          legend-position="bottom"
          show-label
          :colors="ringColors"
          height="16rem"
        />
        <div v-if="!loading && retrievalModeData.length === 0" class="empty-hint">
          暂无应用
        </div>
      </div>
    </div>

    <!-- 下区：文档状态分布 + 最近问答 + 异常/评测 -->
    <div class="bottom-row">
      <!-- 文档状态分布 -->
      <div class="chart-panel art-card-sm">
        <div class="panel-title">文档状态分布</div>
        <div ref="docStatusChartRef" class="chart-canvas" v-loading="loading" />
      </div>

      <!-- 最近问答 -->
      <div class="chart-panel art-card-sm">
        <div class="panel-title">
          最近问答
          <ElButton link type="primary" class="panel-more" @click="goTo('/everkb/qa-record')">
            查看全部
          </ElButton>
        </div>
        <ElTable :data="dashboard?.recent_qa ?? []" size="small" :show-header="false">
          <ElTableColumn min-width="220">
            <template #default="{ row }">
              <span class="qa-question" :title="row.question">{{ row.question }}</span>
            </template>
          </ElTableColumn>
          <ElTableColumn width="70" align="right">
            <template #default="{ row }">
              <ElTag size="small" :type="row.grounded ? 'success' : 'info'" effect="plain">
                {{ row.grounded ? '基于知识库' : '自由回答' }}
              </ElTag>
            </template>
          </ElTableColumn>
          <ElTableColumn width="80" align="right">
            <template #default="{ row }">{{ row.latency_ms }}ms</template>
          </ElTableColumn>
          <ElTableColumn width="60" align="right">
            <template #default="{ row }">
              <ElButton link type="primary" @click="goTrace(row.id)">Trace</ElButton>
            </template>
          </ElTableColumn>
        </ElTable>
        <div v-if="!loading && !dashboard?.recent_qa?.length" class="empty-hint">暂无问答</div>
      </div>
    </div>

    <!-- 底部：异常告警 + 评测结论摘要 -->
    <div class="alert-row">
      <div v-if="alertItems.length" class="alert-panel art-card-sm">
        <div class="panel-title">待处理异常</div>
        <div v-for="item in alertItems" :key="item.label" class="alert-item">
          <span class="alert-label">{{ item.label }}</span>
          <ElButton link type="danger" @click="goTo(item.path)">{{ item.count }} →</ElButton>
        </div>
      </div>

      <div class="alert-panel art-card-sm">
        <div class="panel-title">检索评测结论</div>
        <div v-if="ablation" class="eval-summary">
          <span class="eval-line">
            RRF 混合 <b>{{ toPercent(hybridRecall) }}</b> vs 纯向量
            {{ toPercent(denseRecall) }}（Recall@{{ ablation.top_k }}）
          </span>
          <ElButton link type="primary" @click="goTo('/everkb/eval')">查看评测 →</ElButton>
        </div>
        <div v-else class="empty-hint">暂无评测数据</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
  import { useRouter } from 'vue-router'
  import ArtRingChart from '@/components/core/charts/art-ring-chart/index.vue'
  import ArtStatsCard from '@/components/core/cards/art-stats-card/index.vue'
  import { fetchDashboard } from '@/api/everkb/dashboard'
  import { fetchAblationResult } from '@/api/everkb/eval'
  import { useChartComponent } from '@/hooks/core/useChart'
  import type { EChartsOption } from '@/plugins/echarts'
  import { DOC_STATUS } from '@/constants/everkb'

  defineOptions({ name: 'EverKBDashboard' })

  const router = useRouter()
  const loading = ref(true)
  const dashboard = ref<Api.EverKB.Dashboard | null>(null)
  const ablation = ref<Api.EverKB.AblationResult | null>(null)

  const toPercent = (v: number) => `${(v * 100).toFixed(1)}%`

  // ── KPI 卡片配置 ──────────────────────────────────────────────
  const statCards = computed(() => {
    const d = dashboard.value
    return [
      {
        label: '知识库',
        value: d?.kb_count ?? 0,
        description: '知识库总数',
        icon: 'ri:database-2-line',
        iconStyle: 'bg-primary',
        path: '/everkb/knowledge'
      },
      {
        label: '文档',
        value: d?.doc_count ?? 0,
        description: '文档总数',
        icon: 'ri:file-text-line',
        iconStyle: 'bg-info',
        path: '/everkb/document',
        alert: d?.failed_doc_count ? `${d.failed_doc_count} 失败` : undefined
      },
      {
        label: 'Chunk',
        value: d?.chunk_count ?? 0,
        description: '切块总数',
        icon: 'ri:stack-line',
        iconStyle: 'bg-success',
        path: '/everkb/chunk'
      },
      {
        label: '应用',
        value: d?.app_count ?? 0,
        description: '应用总数',
        icon: 'ri:robot-2-line',
        iconStyle: 'bg-secondary',
        path: '/everkb/app'
      },
      {
        label: '问答',
        value: d?.qa_count ?? 0,
        description: '累计问答数',
        icon: 'ri:chat-3-line',
        iconStyle: 'bg-warning',
        path: '/everkb/qa-record'
      },
      {
        label: '花费',
        value: d?.total_cost ?? 0,
        description: '累计花费（¥）',
        icon: 'ri:money-cny-circle-line',
        iconStyle: 'bg-danger',
        path: '/everkb/trace',
        decimals: 4
      }
    ]
  })

  // ── 趋势图 ──────────────────────────────────────────────────
  const trendData = computed(() => dashboard.value?.qa_trend ?? [])

  const { chartRef: trendChartRef } = useChartComponent({
    props: { height: '16rem', loading: false, isEmpty: false },
    checkEmpty: () => !trendData.value.length,
    watchSources: [() => dashboard.value],
    generateOptions: (): EChartsOption => {
      const dates = trendData.value.map((p) => p.date.slice(5)) // MM-DD
      const counts = trendData.value.map((p) => p.count)
      return {
        tooltip: { trigger: 'axis' },
        grid: { top: 20, right: 16, bottom: 28, left: 40 },
        xAxis: {
          type: 'category',
          data: dates,
          axisLabel: { color: '#999', fontSize: 11 }
        },
        yAxis: {
          type: 'value',
          minInterval: 1,
          axisLabel: { color: '#999' }
        },
        series: [
          {
            name: '问答数',
            type: 'line',
            data: counts,
            smooth: true,
            symbolSize: 5,
            itemStyle: { color: '#409EFF' },
            areaStyle: { opacity: 0.12 }
          }
        ]
      }
    }
  })

  // ── 检索模式环形图数据 ───────────────────────────────────────
  const ringColors = ['#409EFF', '#14DEBA']
  const retrievalModeData = computed(() =>
    (dashboard.value?.retrieval_modes ?? []).map((m) => ({
      name: m.mode === 'hybrid' ? '混合检索' : '纯向量',
      value: m.count
    }))
  )

  // ── 文档状态分布图 ───────────────────────────────────────────
  const DOC_STATUS_LABEL: Record<number, string> = {
    [DOC_STATUS.Uploaded]: '已上传',
    [DOC_STATUS.Parsing]: '解析中',
    [DOC_STATUS.Extracted]: '已抽取',
    [DOC_STATUS.Chunked]: '已切块',
    [DOC_STATUS.Vectorizing]: '向量化中',
    [DOC_STATUS.Completed]: '已完成',
    [DOC_STATUS.Failed]: '失败'
  }

  const docStatusData = computed(() => dashboard.value?.doc_status ?? [])

  const { chartRef: docStatusChartRef } = useChartComponent({
    props: { height: '16rem', loading: false, isEmpty: false },
    checkEmpty: () => !docStatusData.value.length,
    watchSources: [() => dashboard.value],
    generateOptions: (): EChartsOption => {
      const labels = docStatusData.value.map((d) => DOC_STATUS_LABEL[d.status] ?? `状态${d.status}`)
      const counts = docStatusData.value.map((d) => d.count)
      return {
        tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
        grid: { top: 20, right: 16, bottom: 28, left: 40 },
        xAxis: { type: 'category', data: labels, axisLabel: { color: '#999', fontSize: 11 } },
        yAxis: { type: 'value', minInterval: 1, axisLabel: { color: '#999' } },
        series: [
          {
            name: '文档数',
            type: 'bar',
            data: counts,
            barWidth: '45%',
            itemStyle: { color: '#67C23A', borderRadius: [3, 3, 0, 0] }
          }
        ]
      }
    }
  })

  // ── 异常告警 ────────────────────────────────────────────────
  const alertItems = computed(() => {
    const d = dashboard.value
    const items: { label: string; count: number; path: string }[] = []
    if (d?.failed_doc_count) {
      items.push({ label: '失败文档', count: d.failed_doc_count, path: '/everkb/document' })
    }
    return items
  })

  // ── 评测结论摘要 ────────────────────────────────────────────
  const hybridRecall = computed(
    () => ablation.value?.results.find((r) => r.key === 'hybrid')?.recall_at_k ?? 0
  )
  const denseRecall = computed(
    () => ablation.value?.results.find((r) => r.key === 'dense')?.recall_at_k ?? 0
  )

  const goTo = (path: string) => router.push({ path })
  const goTrace = (id: number) =>
    router.push({ path: '/everkb/trace-detail', query: { traceId: String(id) } })

  onMounted(async () => {
    try {
      dashboard.value = await fetchDashboard()
    } catch {
      // http 层已弹错误
    } finally {
      loading.value = false
    }
    // 评测结论非关键路径，独立加载，失败不阻塞
    try {
      ablation.value = await fetchAblationResult()
    } catch {
      ablation.value = null
    }
  })
</script>

<style lang="scss" scoped>
  .dashboard-page {
    padding: 16px;

    .stats-grid {
      display: grid;
      grid-template-columns: repeat(6, 1fr);
      gap: 16px;
      margin-bottom: 16px;

      .stat-card-link {
        position: relative;
        cursor: pointer;

        .stat-badge {
          position: absolute;
          top: -6px;
          right: -6px;
        }
      }
    }

    .chart-row,
    .bottom-row {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 16px;
      margin-bottom: 16px;
    }

    .chart-panel,
    .alert-panel {
      padding: 16px;

      .panel-title {
        display: flex;
        align-items: center;
        justify-content: space-between;
        font-size: 14px;
        font-weight: 600;
        margin-bottom: 12px;

        .panel-more {
          font-size: 12px;
          font-weight: 400;
        }
      }
    }

    .chart-canvas {
      width: 100%;
      height: 16rem;
    }

    .empty-hint {
      color: var(--art-gray-400, #c0c4cc);
      font-size: 13px;
      text-align: center;
      padding: 24px 0;
    }

    .qa-question {
      display: inline-block;
      max-width: 100%;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      vertical-align: middle;
    }

    .alert-row {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 16px;

      .alert-item {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 8px 0;

        .alert-label {
          color: var(--art-gray-700, #606266);
        }
      }

      .eval-summary {
        display: flex;
        align-items: center;
        justify-content: space-between;

        .eval-line {
          color: var(--art-gray-700, #606266);

          b {
            color: var(--el-color-success, #67c23a);
          }
        }
      }
    }
  }
</style>
