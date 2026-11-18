import request from '@/utils/http'

/**
 * EverKB 问答记录 API（对齐后端 /api/v1/admin/records，Task 22）
 * qa_record = 一条 Trace 的主表（traceId = qa_record.id）。
 * 注意：用户反馈的提交端点在 open 侧（POST /api/v1/apps/{id}/feedback，X-API-Key 鉴权），
 * 管理后台一期只读浏览 + 反馈筛选，不在此提交反馈。
 */

/** 问答记录分页列表（可按 app_id / feedback 筛选，id 倒序） */
export function fetchQaRecordPage(params: Api.EverKB.QaRecordPageParams = {}) {
  return request.get<Api.EverKB.QaRecordPage>({
    url: '/api/v1/admin/records',
    params
  })
}

/** 单条问答记录详情（含 citations） */
export function fetchQaRecordDetail(id: number) {
  return request.get<Api.EverKB.QaRecord>({
    url: `/api/v1/admin/records/${id}`
  })
}
