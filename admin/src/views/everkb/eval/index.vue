<template>
  <div class="eval-page">
    <!-- 元信息卡 -->
    <div v-if="!loading && result" class="meta-bar art-card-sm">
      <div class="meta-item">
        <span class="meta-label">评测库</span>
        <span class="meta-value">{{ result.eval_kb }}</span>
      </div>
      <div class="meta-item">
        <span class="meta-label">评测集</span>
        <span class="meta-value">{{ result.n_items }} 条（seed={{ result.seed }}）</span>
      </div>
      <div class="meta-item">
        <span class="meta-label">Chunk 规模</span>
        <span class="meta-value">{{ result.n_chunks }}</span>
      </div>
      <div class="meta-item">
        <span class="meta-label">Top-K</span>
        <span class="meta-value">{{ result.top_k }}</span>
      </div>
      <div class="meta-item">
        <span class="meta-label">RRF 参数</span>
        <span class="meta-value">k={{ result.rrf_k }} · oversample={{ result.oversample }}</span>
      </div>
      <div class="meta-item">
        <span class="meta-label">生成时间</span>
        <span class="meta-value">{{ formatTime(result.generated_at) }}</span>
      </div>
    </div>

    <!-- 三路指标对比柱状图 -->
    <div class="chart-card art-card-sm">
      <div class="section-title">三路检索指标对比（Recall@k / MRR / Hit@k）</div>
      <div v-if="!loading && result" ref="chartRef" class="chart-canvas" />
      <div v-else class="chart-empty" v-loading="loading" />
    </div>

    <!-- 明细表 -->
    <div class="table-card art-card-sm">
      <div class="section-title">指标明细</div>
      <ElTable :data="result?.results ?? []" size="small" border>
        <ElTableColumn prop="label" label="检索方式" min-width="140" />
        <ElTableColumn label="Recall@k" width="140" align="right">
          <template #default="{ row }">
            <span class="metric-cell" :class="{ best: row.key === bestKey }">
              {{ toPercent(row.recall_at_k) }}
            </span>
          </template>
        </ElTableColumn>
        <ElTableColumn label="MRR" width="120" align="right">
          <template #default="{ row }">
            <span class="metric-cell" :class="{ best: row.key === bestMrrKey }">
              {{ toPercent(row.mrr) }}
            </span>
          </template>
        </ElTableColumn>
        <ElTableColumn label="Hit@k" width="120" align="right">
          <template #default="{ row }">
            <span class="metric-cell" :class="{ best: row.key === bestHitKey }">
              {{ toPercent(row.hit_at_k) }}
            </span>
          </template>
        </ElTableColumn>
      </ElTable>
    </div>

    <!-- 结论与方法局限 -->
    <div class="conclusion art-card-sm">
      <div class="section-title">结论</div>
      <p class="conclusion-text">
        RRF 混合检索在 Recall@k 上不劣于单路（且通常更稳），印证「关键词精确 + 语义召回互补」的价值——法条检索中近义表述、专有名词、交叉引用场景下，纯向量易漏关键词命中，纯 BM25 易漏语义改写，混合互补。
      </p>
      <div class="section-title" style="margin-top: 16px">方法局限（如实说明）</div>
      <ul class="limits">
        <li>合成法 ground truth 偏乐观：<code>relevant_chunk_ids</code> 假设「query 应命中来源 chunk 自身」，但 LLM 白话改写后的 query 可能命中语义等价的其他 chunk，导致三路指标普遍偏高、区分度被压缩。已预留人工抽检 10% 入口修正。</li>
        <li>评测集规模有限：{{ result?.n_chunks ?? 0 }} chunk 抽样 {{ result?.n_items ?? 0 }} 条，消融实验的分辨率受限于法规包体量。</li>
        <li>RRF 参数：k=60（经典默认值），oversample=4，未做参数扫描。</li>
      </ul>
    </div>
  </div>
</template>

<script setup lang="ts">
  import { fetchAblationResult } from '@/api/everkb/eval'
  import { useChartComponent } from '@/hooks/core/useChart'
  import type { EChartsOption } from '@/plugins/echarts'

  defineOptions({ name: 'EverKBEval' })

  const loading = ref(true)
  const result = ref<Api.EverKB.AblationResult | null>(null)

  const toPercent = (v: number) => `${(v * 100).toFixed(1)}%`

  const formatTime = (iso: string) => iso?.replace('T', ' ').slice(0, 19) || '-'

  // 三路各自的 Recall 最高者（用于明细表高亮）
  const bestKey = computed(() => {
    if (!result.value?.results.length) return ''
    return result.value.results.reduce((a, b) => (a.recall_at_k >= b.recall_at_k ? a : b)).key
  })
  const bestMrrKey = computed(() => {
    if (!result.value?.results.length) return ''
    return result.value.results.reduce((a, b) => (a.mrr >= b.mrr ? a : b)).key
  })
  const bestHitKey = computed(() => {
    if (!result.value?.results.length) return ''
    return result.value.results.reduce((a, b) => (a.hit_at_k >= b.hit_at_k ? a : b)).key
  })

  // 分组柱状图：x 轴 = 检索方式，三组 = Recall@k / MRR / Hit@k
  const { chartRef } = useChartComponent({
    props: { height: '20rem', loading: false, isEmpty: false },
    checkEmpty: () => !result.value?.results.length,
    watchSources: [() => result.value],
    generateOptions: (): EChartsOption => {
      const labels = (result.value?.results ?? []).map((r) => r.label)
      const metricNames = ['Recall@k', 'MRR', 'Hit@k']
      const metricKeys = ['recall_at_k', 'mrr', 'hit_at_k'] as const
      const colors = ['#4A90E2', '#F5A623', '#14DEBA']

      return {
        color: colors,
        tooltip: {
          trigger: 'axis',
          axisPointer: { type: 'shadow' },
          valueFormatter: (v: unknown) => `${((v as number) * 100).toFixed(1)}%`
        },
        legend: { data: metricNames, top: 0 },
        grid: { top: 36, right: 16, bottom: 28, left: 48 },
        xAxis: { type: 'category', data: labels },
        yAxis: {
          type: 'value',
          max: 1,
          axisLabel: { formatter: (v: number) => `${(v * 100).toFixed(0)}%` }
        },
        series: metricKeys.map((k, i) => ({
          name: metricNames[i],
          type: 'bar' as const,
          barWidth: '18%',
          data: (result.value?.results ?? []).map((r) => r[k]),
          itemStyle: { borderRadius: [3, 3, 0, 0] }
        }))
      }
    }
  })

  onMounted(async () => {
    try {
      result.value = await fetchAblationResult()
    } catch {
      // http 层已弹错误（如结果文件缺失）
    } finally {
      loading.value = false
    }
  })
</script>

<style lang="scss" scoped>
  .eval-page {
    padding: 16px;

    .meta-bar {
      display: flex;
      flex-wrap: wrap;
      gap: 32px;
      padding: 16px;
      margin-bottom: 16px;

      .meta-item {
        display: flex;
        flex-direction: column;
        gap: 4px;

        .meta-label {
          font-size: 12px;
          color: var(--art-gray-500, #909399);
        }

        .meta-value {
          font-size: 14px;
          font-weight: 600;
          font-variant-numeric: tabular-nums;
        }
      }
    }

    .chart-card,
    .table-card,
    .conclusion {
      padding: 16px;
      margin-bottom: 16px;
    }

    .section-title {
      font-size: 14px;
      font-weight: 600;
      margin-bottom: 14px;
    }

    .chart-canvas {
      width: 100%;
      height: 20rem;
    }

    .chart-empty {
      height: 20rem;
    }

    .metric-cell {
      font-variant-numeric: tabular-nums;

      &.best {
        color: var(--el-color-success, #67c23a);
        font-weight: 700;
      }
    }

    .conclusion-text {
      margin: 0;
      line-height: 1.7;
      color: var(--art-gray-700, #606266);
    }

    .limits {
      margin: 0;
      padding-left: 20px;
      line-height: 1.7;
      color: var(--art-gray-600, #909399);

      code {
        background: var(--art-gray-100, #f5f7fa);
        padding: 1px 6px;
        border-radius: 3px;
        font-size: 12px;
      }
    }
  }
</style>
