import request from '@/utils/http'

/**
 * EverKB Trace 查看器 API（对齐后端 /api/v1/admin/traces，Task 22）
 * span 树由后端按 parent_span_id 直接组好（TraceTreeOut.spans），前端仅递归渲染。
 * 列表入口复用 /records（qa_record 即一条 Trace 的主表）。
 */

/** 单条问答的 span 树（后端已组树，spans 为根节点列表） */
export function fetchTraceTree(recordId: number) {
  return request.get<Api.EverKB.TraceTree>({
    url: `/api/v1/admin/traces/${recordId}`
  })
}

/** 跨 Trace 聚合：最慢调用 Top N + 各 span_type P95/平均 token/平均花费 */
export function fetchTraceAggregation() {
  return request.get<Api.EverKB.TraceAggregation>({
    url: '/api/v1/admin/traces/aggregate'
  })
}
