<template>
  <div class="trace-detail-page">
    <div class="page-head">
      <ElButton link @click="goBack">
        <el-icon class="mr-1"><Back /></el-icon>
        {{ $t('everkb.traceDetail.backToList') }}
      </ElButton>
      <span class="page-title">
        {{
          $t('everkb.traceDetail.spanTreeTitle', {
            source: isPipeline ? $t('everkb.traceDetail.pipeline') : 'Trace',
            id: traceId
          })
        }}
      </span>
      <ElTag v-if="isPipeline" type="success" effect="plain">{{
        $t('everkb.traceDetail.pipelineTag')
      }}</ElTag>
      <ElTag v-else type="primary" effect="plain">{{ $t('everkb.traceDetail.qaTag') }}</ElTag>
    </div>

    <!-- 管线 Trace 附文档信息 -->
    <div v-if="isPipeline && tree?.doc" class="doc-bar art-card-sm">
      <div class="doc-item">
        <span class="doc-label">{{ $t('everkb.traceDetail.doc') }}</span>
        <span class="doc-value">{{ tree.doc.name }}</span>
      </div>
      <div class="doc-item">
        <span class="doc-label">{{ $t('everkb.traceDetail.docId') }}</span>
        <span class="doc-value">#{{ tree.doc.id }}</span>
      </div>
      <div class="doc-item">
        <span class="doc-label">{{ $t('everkb.traceDetail.kb') }}</span>
        <span class="doc-value">#{{ tree.doc.kb_id }}</span>
      </div>
      <div class="doc-item">
        <span class="doc-label">{{ $t('everkb.traceDetail.docStatus') }}</span>
        <span class="doc-value">{{ docStatusLabel(tree.doc.status) }}</span>
      </div>
    </div>

    <div
      v-if="loading"
      v-loading="true"
      :element-loading-text="$t('everkb.traceDetail.loading')"
      class="detail-loading"
    />
    <ElEmpty
      v-else-if="!tree || !tree.spans.length"
      :description="$t('everkb.traceDetail.empty')"
    />
    <template v-else>
      <div class="summary-bar art-card-sm">
        <div class="summary-item">
          <span class="summary-label">{{ $t('everkb.traceDetail.spanTotal') }}</span>
          <span class="summary-value">{{ spanCount }}</span>
        </div>
        <div class="summary-item">
          <span class="summary-label">{{ $t('everkb.traceDetail.totalLatency') }}</span>
          <span class="summary-value">{{ totalLatency }}ms</span>
        </div>
        <div class="summary-item">
          <span class="summary-label">{{ $t('everkb.traceDetail.totalCost') }}</span>
          <span class="summary-value">¥{{ totalCost }}</span>
        </div>
      </div>

      <div class="tree-container art-card-sm">
        <SpanTreeNode v-for="node in tree.spans" :key="node.id" :span="node" />
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
  import { useI18n } from 'vue-i18n'
  import { ElMessage } from 'element-plus'
  import { Back } from '@element-plus/icons-vue'
  import { useRoute, useRouter } from 'vue-router'
  import { fetchTraceTree } from '@/api/everkb/trace'
  import SpanTreeNode from './components/SpanTreeNode.vue'

  defineOptions({ name: 'EverKBTraceDetail' })

  const { t } = useI18n()
  const route = useRoute()
  const router = useRouter()
  const traceId = Number(route.query.traceId ?? route.query.recordId ?? 0)

  const loading = ref(true)
  const tree = ref<Api.EverKB.TraceTree | null>(null)

  const isPipeline = computed(() => tree.value?.source === 'pipeline')

  const docStatusLabel = (s: number) => {
    const labels: Record<number, string> = {
      1: t('everkb.traceDetail.docStatusUploaded'),
      2: t('everkb.traceDetail.docStatusParsing'),
      3: t('everkb.traceDetail.docStatusExtracted'),
      4: t('everkb.traceDetail.docStatusChunked'),
      5: t('everkb.traceDetail.docStatusVectorizing'),
      6: t('everkb.traceDetail.docStatusCompleted'),
      7: t('everkb.traceDetail.docStatusFailed')
    }
    return labels[s] ?? t('everkb.traceDetail.docStatusUnknown', { n: s })
  }

  // 统计：扁平化遍历 span 树
  const spanCount = computed(() => {
    if (!tree.value) return 0
    let count = 0
    const walk = (nodes: Api.EverKB.TraceSpanNode[]) => {
      for (const n of nodes) {
        count += 1
        if (n.children?.length) walk(n.children)
      }
    }
    walk(tree.value.spans)
    return count
  })

  const totalLatency = computed(() => {
    if (!tree.value) return 0
    let sum = 0
    const walk = (nodes: Api.EverKB.TraceSpanNode[]) => {
      for (const n of nodes) {
        sum += n.latency_ms ?? 0
        if (n.children?.length) walk(n.children)
      }
    }
    walk(tree.value.spans)
    return sum
  })

  const totalCost = computed(() => {
    if (!tree.value) return '0'
    let sum = 0
    const walk = (nodes: Api.EverKB.TraceSpanNode[]) => {
      for (const n of nodes) {
        sum += n.cost ?? 0
        if (n.children?.length) walk(n.children)
      }
    }
    walk(tree.value.spans)
    return sum.toFixed(6)
  })

  const goBack = () => {
    router.push({ path: '/everkb/trace' })
  }

  onMounted(async () => {
    if (!traceId) {
      ElMessage.warning(t('everkb.traceDetail.missingTraceId'))
      loading.value = false
      return
    }
    try {
      tree.value = await fetchTraceTree(traceId)
    } catch {
      // http 层已弹错误（404 等）
    } finally {
      loading.value = false
    }
  })
</script>

<style lang="scss" scoped>
  .trace-detail-page {
    padding: 16px;

    .page-head {
      display: flex;
      align-items: center;
      gap: 12px;
      margin-bottom: 16px;

      .page-title {
        font-size: 16px;
        font-weight: 600;
      }
    }

    .doc-bar {
      display: flex;
      flex-wrap: wrap;
      gap: 32px;
      padding: 16px;
      margin-bottom: 12px;

      .doc-item {
        display: flex;
        flex-direction: column;
        gap: 4px;

        .doc-label {
          font-size: 12px;
          color: var(--art-gray-500, #909399);
        }

        .doc-value {
          font-size: 14px;
          font-weight: 600;
        }
      }
    }

    .detail-loading {
      min-height: 300px;
    }

    .summary-bar {
      display: flex;
      gap: 40px;
      padding: 16px;
      margin-bottom: 12px;

      .summary-item {
        display: flex;
        flex-direction: column;
        gap: 4px;

        .summary-label {
          font-size: 12px;
          color: var(--art-gray-500, #909399);
        }

        .summary-value {
          font-size: 20px;
          font-weight: 600;
          font-variant-numeric: tabular-nums;
        }
      }
    }

    .tree-container {
      padding: 12px;
    }
  }
</style>
