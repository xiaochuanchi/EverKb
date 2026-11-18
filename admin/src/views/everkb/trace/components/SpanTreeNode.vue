<template>
  <div class="span-node">
    <div class="span-row" @click="toggle">
      <el-icon class="span-caret" :class="{ 'is-leaf': !hasChildren }">
        <ArrowRight v-if="hasChildren" :class="{ expanded }" />
        <span v-else class="dot">·</span>
      </el-icon>

      <ElTag
        size="small"
        :type="TYPE_META[span.span_type]?.tag || 'info'"
        effect="light"
        class="span-type"
      >
        {{ TYPE_META[span.span_type]?.label || span.span_type }}
      </ElTag>

      <span class="span-name" :title="span.name">{{ span.name }}</span>

      <span class="span-latency" :class="{ slow: span.latency_ms >= 1000 }"
        >{{ span.latency_ms }}ms</span
      >

      <span
        v-if="span.gen_ai_usage_tokens_in != null || span.gen_ai_usage_tokens_out != null"
        class="span-tokens"
      >
        {{ span.gen_ai_usage_tokens_in ?? 0 }}↑ {{ span.gen_ai_usage_tokens_out ?? 0 }}↓
      </span>

      <span v-if="span.cost != null" class="span-cost">¥{{ span.cost.toFixed(6) }}</span>

      <span class="span-time">{{ formatTime(span.start_time) }}</span>
    </div>

    <div v-if="expanded" class="span-detail">
      <div v-if="span.input_summary" class="span-summary">
        <span class="span-summary-label">输入</span>
        <span class="span-summary-text">{{ span.input_summary }}</span>
      </div>
      <div v-if="span.output_summary" class="span-summary">
        <span class="span-summary-label">输出</span>
        <span class="span-summary-text">{{ span.output_summary }}</span>
      </div>
    </div>

    <div v-if="expanded && hasChildren" class="span-children">
      <SpanTreeNode v-for="child in span.children" :key="child.id" :span="child" />
    </div>
  </div>
</template>

<script setup lang="ts">
  import { ArrowRight } from '@element-plus/icons-vue'

  defineOptions({ name: 'SpanTreeNode' })

  const props = defineProps<{ span: Api.EverKB.TraceSpanNode }>()

  const TYPE_META: Record<
    string,
    { label: string; tag: 'info' | 'success' | 'primary' | 'warning' | 'danger' }
  > = {
    embedding: { label: '嵌入', tag: 'primary' },
    retrieval: { label: '检索', tag: 'success' },
    db: { label: '数据库', tag: 'info' },
    llm: { label: 'LLM', tag: 'warning' },
    tool: { label: '工具', tag: 'info' },
    agent_step: { label: '编排', tag: 'info' }
  }

  const expanded = ref(true)
  const hasChildren = computed(() => props.span.children && props.span.children.length > 0)

  const toggle = () => {
    expanded.value = !expanded.value
  }

  const formatTime = (iso: string) => iso?.replace('T', ' ').slice(0, 19) || '-'
</script>

<style lang="scss" scoped>
  .span-node {
    .span-row {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 8px 10px;
      border-radius: 6px;
      cursor: pointer;
      transition: background 0.15s;
      font-size: 13px;

      &:hover {
        background: var(--art-fill-color-light, #f5f7fa);
      }
    }

    .span-caret {
      flex-shrink: 0;
      color: var(--art-gray-500, #aaa);
      font-size: 14px;
      width: 14px;

      .expanded {
        transform: rotate(90deg);
        transition: transform 0.15s;
      }

      &.is-leaf .dot {
        font-size: 18px;
        line-height: 1;
      }
    }

    .span-type {
      flex-shrink: 0;
    }

    .span-name {
      font-weight: 600;
      color: var(--art-text-color-primary, #303133);
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      max-width: 320px;
    }

    .span-latency {
      flex-shrink: 0;
      font-variant-numeric: tabular-nums;
      color: var(--art-gray-700, #606266);

      &.slow {
        color: var(--el-color-danger, #f56c6c);
        font-weight: 600;
      }
    }

    .span-tokens {
      flex-shrink: 0;
      font-size: 12px;
      color: var(--art-gray-500, #909399);
    }

    .span-cost {
      flex-shrink: 0;
      font-size: 12px;
      color: var(--art-gray-500, #909399);
      font-variant-numeric: tabular-nums;
    }

    .span-time {
      flex-shrink: 0;
      margin-left: auto;
      font-size: 12px;
      color: var(--art-gray-400, #c0c4cc);
    }

    .span-detail {
      padding: 0 10px 4px 32px;
    }

    .span-summary {
      display: flex;
      gap: 6px;
      margin-top: 4px;
      font-size: 12px;
      line-height: 1.6;

      .span-summary-label {
        flex-shrink: 0;
        color: var(--art-color-primary, #409eff);
        font-weight: 600;
      }

      .span-summary-text {
        color: var(--art-gray-600, #888);
        word-break: break-word;
      }
    }

    .span-children {
      padding-left: 20px;
      border-left: 1px solid var(--art-border-color-light, #ebeef5);
      margin-left: 14px;
    }
  }
</style>
