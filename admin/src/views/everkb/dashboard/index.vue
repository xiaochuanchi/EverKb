<template>
  <div class="dashboard-page">
    <!-- 顶部 KPI 统计卡片（可点击下钻，含环比） -->
    <div class="stats-grid">
      <div
        v-for="card in statCards"
        :key="card.label"
        class="stat-card art-card"
        :class="{ 'has-alert': card.alert }"
        @click="goTo(card.path)"
      >
        <div class="stat-top">
          <div class="stat-icon" :class="card.iconStyle">
            <ArtSvgIcon :icon="card.icon" />
          </div>
          <div class="stat-value">
            <ArtCountTo
              :target="card.value"
              :duration="1200"
              :decimals="card.decimals ?? 0"
              separator=","
            />
          </div>
          <el-icon class="stat-arrow"><ArrowRight /></el-icon>
        </div>
        <div class="stat-bottom">
          <span class="stat-label">{{ card.label }}</span>
          <span class="stat-mom" :class="momClass(card.trend)">
            {{ momLabel(card.trend) }}
          </span>
        </div>
        <ElBadge v-if="card.alert" :value="card.alert" class="stat-badge" type="danger" />
      </div>
    </div>

    <!-- 中区：趋势图 + 分布图 -->
    <div class="chart-row">
      <div class="chart-panel art-card-sm">
        <div class="panel-title">{{ $t('everkb.dashboard.trendTitle') }}</div>
        <div ref="trendChartRef" class="chart-canvas" v-loading="loading" />
      </div>

      <div class="chart-panel art-card-sm">
        <div class="panel-title">{{ $t('everkb.dashboard.retrievalTitle') }}</div>
        <ArtRingChart
          :data="retrievalModeData"
          :show-legend="true"
          legend-position="bottom"
          show-label
          :colors="ringColors"
          height="16rem"
        />
        <div v-if="!loading && retrievalModeData.length === 0" class="empty-hint">
          {{ $t('everkb.dashboard.noApps') }}
        </div>
      </div>
    </div>

    <!-- 下区：文档状态分布 + 最近问答 + 异常/评测 -->
    <div class="bottom-row">
      <!-- 文档状态分布 -->
      <div class="chart-panel art-card-sm">
        <div class="panel-title">{{ $t('everkb.dashboard.docStatusTitle') }}</div>
        <div ref="docStatusChartRef" class="chart-canvas" v-loading="loading" />
      </div>

      <!-- 最近问答 -->
      <div class="chart-panel art-card-sm">
        <div class="panel-title">
          {{ $t('everkb.dashboard.recentQaTitle') }}
          <ElButton link type="primary" class="panel-more" @click="goTo('/everkb/qa-record')">
            {{ $t('everkb.dashboard.viewAll') }}
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
                {{
                  row.grounded ? $t('everkb.dashboard.grounded') : $t('everkb.dashboard.freeAnswer')
                }}
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
        <div v-if="!loading && !dashboard?.recent_qa?.length" class="empty-hint">
          {{ $t('everkb.dashboard.noQa') }}
        </div>
      </div>
    </div>

    <!-- 底部：异常告警 + 评测结论摘要 -->
    <div class="alert-row">
      <div v-if="alertItems.length" class="alert-panel art-card-sm">
        <div class="panel-title">{{ $t('everkb.dashboard.pendingAlerts') }}</div>
        <div v-for="item in alertItems" :key="item.label" class="alert-item">
          <span class="alert-label">{{ item.label }}</span>
          <ElButton link type="danger" @click="goTo(item.path)">{{ item.count }} →</ElButton>
        </div>
      </div>

      <div class="alert-panel art-card-sm">
        <div class="panel-title">{{ $t('everkb.dashboard.evalTitle') }}</div>
        <div v-if="ablation" class="eval-summary">
          <span class="eval-line">
            {{ $t('everkb.dashboard.rrfHybrid') }} <b>{{ toPercent(hybridRecall) }}</b> vs
            {{
              $t('everkb.dashboard.denseRecall', {
                dense: toPercent(denseRecall),
                n: ablation.top_k
              })
            }}
          </span>
          <ElButton link type="primary" @click="goTo('/everkb/eval')">
            {{ $t('everkb.dashboard.viewEval') }}
          </ElButton>
        </div>
        <div v-else class="empty-hint">{{ $t('everkb.dashboard.noEval') }}</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
  import { useRouter } from 'vue-router'
  import { useI18n } from 'vue-i18n'
  import { ArrowRight } from '@element-plus/icons-vue'
  import ArtRingChart from '@/components/core/charts/art-ring-chart/index.vue'
  import { fetchDashboard } from '@/api/everkb/dashboard'
  import { fetchAblationResult } from '@/api/everkb/eval'
  import { useChartComponent } from '@/hooks/core/useChart'
  import type { EChartsOption } from '@/plugins/echarts'
  import { DOC_STATUS } from '@/constants/everkb'

  defineOptions({ name: 'EverKBDashboard' })

  const router = useRouter()
  const { t } = useI18n()
  const loading = ref(true)
  const dashboard = ref<Api.EverKB.Dashboard | null>(null)
  const ablation = ref<Api.EverKB.AblationResult | null>(null)

  const toPercent = (v: number) => `${(v * 100).toFixed(1)}%`

  // ── 环比辅助（红涨绿跌，A 股惯例）─────────────────────────────
  const momLabel = (trend?: Api.EverKB.DashboardKpiTrend) => {
    if (!trend || trend.pct_change == null) return '—'
    const pct = (trend.pct_change * 100).toFixed(0)
    return trend.pct_change >= 0 ? `+${pct}%` : `${pct}%`
  }
  const momClass = (trend?: Api.EverKB.DashboardKpiTrend) => {
    if (!trend || trend.pct_change == null) return 'mom-flat'
    return trend.pct_change >= 0 ? 'mom-up' : 'mom-down'
  }

  // ── KPI 卡片配置 ──────────────────────────────────────────────
  const statCards = computed(() => {
    const d = dashboard.value
    const kpi = d?.kpi_trend ?? {}
    return [
      {
        label: t('everkb.dashboard.totalKb'),
        value: d?.kb_count ?? 0,
        icon: 'ri:database-2-line',
        iconStyle: 'bg-primary',
        path: '/everkb/knowledge',
        trend: kpi.kb
      },
      {
        label: t('everkb.dashboard.docs'),
        value: d?.doc_count ?? 0,
        icon: 'ri:file-text-line',
        iconStyle: 'bg-info',
        path: '/everkb/document',
        trend: kpi.doc,
        alert: d?.failed_doc_count
          ? t('everkb.dashboard.failedDocsAlert', { n: d.failed_doc_count })
          : undefined
      },
      {
        label: 'Chunk',
        value: d?.chunk_count ?? 0,
        icon: 'ri:stack-line',
        iconStyle: 'bg-success',
        path: '/everkb/document',
        trend: kpi.chunk
      },
      {
        label: t('everkb.dashboard.apps'),
        value: d?.app_count ?? 0,
        icon: 'ri:robot-2-line',
        iconStyle: 'bg-secondary',
        path: '/everkb/app',
        trend: kpi.app
      },
      {
        label: t('everkb.dashboard.qa'),
        value: d?.qa_count ?? 0,
        icon: 'ri:chat-3-line',
        iconStyle: 'bg-warning',
        path: '/everkb/qa-record',
        trend: kpi.qa
      },
      {
        label: t('everkb.dashboard.cost'),
        value: d?.total_cost ?? 0,
        icon: 'ri:money-cny-circle-line',
        iconStyle: 'bg-danger',
        path: '/everkb/trace',
        decimals: 4,
        trend: kpi.cost
      },
      {
        label: t('everkb.dashboard.drift'),
        value: d?.drift_doc_count ?? 0,
        icon: 'ri:git-repository-commits-line',
        iconStyle: 'bg-danger',
        path: '/everkb/reconcile',
        alert: d?.drift_doc_count
          ? t('everkb.dashboard.driftDocsAlert', { n: d.drift_doc_count })
          : undefined
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
            name: t('everkb.dashboard.qaCountSeries'),
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
      name:
        m.mode === 'hybrid' ? t('everkb.dashboard.hybridMode') : t('everkb.dashboard.denseMode'),
      value: m.count
    }))
  )

  // ── 文档状态分布图 ───────────────────────────────────────────
  const DOC_STATUS_LABEL_KEY: Record<number, string> = {
    [DOC_STATUS.Uploaded]: 'everkb.dashboard.docStatusUploaded',
    [DOC_STATUS.Parsing]: 'everkb.dashboard.docStatusParsing',
    [DOC_STATUS.Extracted]: 'everkb.dashboard.docStatusExtracted',
    [DOC_STATUS.Chunked]: 'everkb.dashboard.docStatusChunked',
    [DOC_STATUS.Vectorizing]: 'everkb.dashboard.docStatusVectorizing',
    [DOC_STATUS.Completed]: 'everkb.dashboard.docStatusCompleted',
    [DOC_STATUS.Failed]: 'everkb.dashboard.docStatusFailed'
  }

  const docStatusLabel = (status: number) => {
    const key = DOC_STATUS_LABEL_KEY[status]
    return key ? t(key) : t('everkb.dashboard.docStatusUnknown', { n: status })
  }

  const docStatusData = computed(() => dashboard.value?.doc_status ?? [])

  const { chartRef: docStatusChartRef } = useChartComponent({
    props: { height: '16rem', loading: false, isEmpty: false },
    checkEmpty: () => !docStatusData.value.length,
    watchSources: [() => dashboard.value],
    generateOptions: (): EChartsOption => {
      const labels = docStatusData.value.map((d) => docStatusLabel(d.status))
      const counts = docStatusData.value.map((d) => d.count)
      return {
        tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
        grid: { top: 20, right: 16, bottom: 28, left: 40 },
        xAxis: { type: 'category', data: labels, axisLabel: { color: '#999', fontSize: 11 } },
        yAxis: { type: 'value', minInterval: 1, axisLabel: { color: '#999' } },
        series: [
          {
            name: t('everkb.dashboard.docCountSeries'),
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
      items.push({
        label: t('everkb.dashboard.alertFailedDocs'),
        count: d.failed_doc_count,
        path: '/everkb/document'
      })
    }
    if (d?.drift_doc_count) {
      items.push({
        label: t('everkb.dashboard.alertDriftDocs'),
        count: d.drift_doc_count,
        path: '/everkb/reconcile'
      })
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
      grid-template-columns: repeat(7, minmax(0, 1fr));
      gap: 12px;
      margin-bottom: 16px;

      .stat-card {
        position: relative;
        cursor: pointer;
        padding: 14px;
        transition: transform 0.2s;

        &:hover {
          transform: translateY(-3px);
        }

        .stat-top {
          display: flex;
          align-items: center;
          gap: 10px;

          .stat-icon {
            flex-shrink: 0;
            width: 38px;
            height: 38px;
            border-radius: 9px;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #fff;
            font-size: 18px;
          }

          .stat-value {
            flex: 1;
            min-width: 0;
            font-size: 22px;
            font-weight: 600;
            font-variant-numeric: tabular-nums;
            line-height: 1;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
          }

          .stat-arrow {
            flex-shrink: 0;
            color: var(--art-gray-400, #c0c4cc);
            font-size: 14px;
          }
        }

        .stat-bottom {
          display: flex;
          align-items: center;
          justify-content: space-between;
          margin-top: 12px;

          .stat-label {
            font-size: 13px;
            color: var(--art-gray-500, #909399);
          }

          .stat-mom {
            font-size: 12px;
            font-weight: 600;
            font-variant-numeric: tabular-nums;

            &.mom-up {
              color: var(--el-color-danger, #f56c6c);
            }

            &.mom-down {
              color: var(--el-color-success, #67c23a);
            }

            &.mom-flat {
              color: var(--art-gray-400, #c0c4cc);
            }
          }
        }

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
