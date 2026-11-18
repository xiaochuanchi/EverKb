import request from '@/utils/http'

/**
 * EverKB 对账工具 API（对齐后端 /api/v1/admin/reconciliation，Task 13）
 * 扫描 status==6（已完成）文档的漂移：unvectorized（chunk 未入库却显示完成）、
 * count_mismatch（MySQL chunk 数 != Milvus 计数）。返回漂移清单。
 * 一期只读展示；一键重建依赖后端后续补端点，前端暂不提供。
 */

/** 漂移扫描（返回已完成文档的异常清单：{doc_id, issue}[]） */
export function fetchReconciliation() {
  return request.get<Api.EverKB.ReconciliationItem[]>({
    url: '/api/v1/admin/reconciliation'
  })
}
