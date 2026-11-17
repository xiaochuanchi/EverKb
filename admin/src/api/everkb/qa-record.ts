import request from '@/utils/http'

/**
 * EverKB 问答记录 API
 * qa_record = 一条 Trace 的主表（traceId = qaRecord.id）
 */

/** 问答记录分页列表 */
export function fetchQaRecordList(params: Api.EverKB.QaRecordSearchParams) {
  return request.get<Api.Common.PaginatedResponse<Api.EverKB.QaRecord>>({
    url: '/api/qa-records',
    params
  })
}

/** 单条问答详情（含引用 chunk 详情） */
export function fetchQaRecordDetail(id: number) {
  return request.get<Api.EverKB.QaRecord & { citations: Api.EverKB.Citation[] }>({
    url: `/api/qa-records/${id}`
  })
}

/** 用户反馈：1 满意 / -1 不满意 */
export function fetchSubmitFeedback(id: number, feedback: Api.EverKB.Feedback) {
  return request.post<void>({
    url: `/api/qa-records/${id}/feedback`,
    params: { feedback }
  })
}

/** 反馈统计 */
export function fetchFeedbackStats(appId?: number) {
  return request.get<{ positive: number; negative: number; none: number }>({
    url: '/api/qa-records/feedback-stats',
    params: { appId }
  })
}
