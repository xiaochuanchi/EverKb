import request from '@/utils/http'

/**
 * EverKB 检索评测 API（对齐后端 /api/v1/admin/evals，二期 Task 28 可视化）
 * 数据源：data/legal/ablation_result.json（scripts/run_ablation.py 生成）。
 */

/** 三路消融指标（纯向量 / 纯 BM25 / RRF 混合）+ 实验元信息 */
export function fetchAblationResult() {
  return request.get<Api.EverKB.AblationResult>({
    url: '/api/v1/admin/evals/ablation'
  })
}
