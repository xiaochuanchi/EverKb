import request from '@/utils/http'

/**
 * EverKB 平台概况 API（对齐后端 /api/v1/admin/dashboard）
 * 一次性返回概况页全部统计（计数 / 趋势 / 分布 / 最近问答）。
 */

export function fetchDashboard() {
  return request.get<Api.EverKB.Dashboard>({
    url: '/api/v1/admin/dashboard'
  })
}
