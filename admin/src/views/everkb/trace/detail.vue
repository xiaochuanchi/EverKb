<template>
  <div class="trace-detail-page">
    <div class="page-head">
      <ElButton link @click="goBack">
        <el-icon class="mr-1"><Back /></el-icon>
        返回列表
      </ElButton>
      <span class="page-title">
        {{ isPipeline ? '入库链路' : 'Trace' }} #{{ traceId }} 的 Span 树
      </span>
      <ElTag v-if="isPipeline" type="success" effect="plain">文档入库链路</ElTag>
      <ElTag v-else type="primary" effect="plain">问答链路</ElTag>
    </div>

    <!-- 管线 Trace 附文档信息 -->
    <div v-if="isPipeline && tree?.doc" class="doc-bar art-card-sm">
      <div class="doc-item">
        <span class="doc-label">文档</span>
        <span class="doc-value">{{ tree.doc.name }}</span>
      </div>
      <div class="doc-item">
        <span class="doc-label">文档 ID</span>
        <span class="doc-value">#{{ tree.doc.id }}</span>
      </div>
      <div class="doc-item">
        <span class="doc-label">所属知识库</span>
        <span class="doc-value">#{{ tree.doc.kb_id }}</span>
      </div>
      <div class="doc-item">
        <span class="doc-label">文档状态</span>
        <span class="doc-value">{{ docStatusLabel(tree.doc.status) }}</span>
      </div>
    </div>

    <div v-if="loading" v-loading="true" element-loading-text="加载中" class="detail-loading" />
    <ElEmpty v-else-if="!tree || !tree.spans.length" description="该记录暂无 Trace 数据" />
    <template v-else>
      <div class="summary-bar art-card-sm">
        <div class="summary-item">
          <span class="summary-label">Span 总数</span>
          <span class="summary-value">{{ spanCount }}</span>
        </div>
        <div class="summary-item">
          <span class="summary-label">总耗时</span>
          <span class="summary-value">{{ totalLatency }}ms</span>
        </div>
        <div class="summary-item">
          <span class="summary-label">总花费</span>
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
  import { ElMessage } from 'element-plus'
  import { Back } from '@element-plus/icons-vue'
  import { useRoute, useRouter } from 'vue-router'
  import { fetchTraceTree } from '@/api/everkb/trace'
  import SpanTreeNode from './components/SpanTreeNode.vue'

  defineOptions({ name: 'EverKBTraceDetail' })

  const route = useRoute()
  const router = useRouter()
  const traceId = Number(route.query.traceId ?? route.query.recordId ?? 0)

  const loading = ref(true)
  const tree = ref<Api.EverKB.TraceTree | null>(null)

  const isPipeline = computed(() => tree.value?.source === 'pipeline')

  const DOC_STATUS_LABEL: Record<number, string> = {
    1: '已上传',
    2: '解析中',
    3: '已提取',
    4: '已切块',
    5: '向量化中',
    6: '已完成',
    7: '失败'
  }
  const docStatusLabel = (s: number) => DOC_STATUS_LABEL[s] ?? `状态 ${s}`

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
      ElMessage.warning('缺少 traceId 参数')
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
