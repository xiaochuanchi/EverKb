import request from '@/utils/http'

/**
 * EverKB 对账工具 API
 * 反目标防线：MySQL 与 Milvus 数据不一致必须有对账手段（设计文档 §2.5）
 */

/** 漂移扫描（vectorized 标志 vs Milvus 实际存在） */
export function fetchReconcileScan() {
  return request.get<Api.EverKB.ReconcileReport>({
    url: '/api/reconcile/scan'
  })
}

/** 一键重建（按 chunkIdsToRebuild 重嵌 + 重入库） */
export function fetchReconcileRebuild(chunkIds: number[]) {
  return request.post<{ rebuilt: number }>({
    url: '/api/reconcile/rebuild',
    params: { chunkIds },
    timeout: 300000
  })
}
