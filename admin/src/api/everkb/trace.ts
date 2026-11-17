import request from '@/utils/http'

/**
 * EverKB Trace 查看器 API
 * span 树按 parentSpanId 渲染，任意深度（二期 Agent 编排零改动接入）
 */

/** Trace 分页列表（关联 qa_record 摘要） */
export function fetchTraceList(params: Api.EverKB.TraceSearchParams) {
  return request.get<Api.Common.PaginatedResponse<Api.EverKB.QaRecord>>({
    url: '/api/traces',
    params
  })
}

/** 单条 Trace 的 Span 全集（前端按 parentSpanId 组树） */
export function fetchTraceSpans(traceId: number) {
  return request.get<Api.EverKB.TraceSpan[]>({
    url: `/api/traces/${traceId}/spans`
  })
}

/** 跨 Trace 聚合：最慢调用 Top N、各步骤 P95 */
export function fetchTraceAggregation() {
  return request.get<Api.EverKB.TraceAggregation>({
    url: '/api/traces/aggregation'
  })
}
