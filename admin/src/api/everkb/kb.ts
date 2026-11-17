import request from '@/utils/http'

/**
 * EverKB 知识库管理 API
 */

/** 知识库列表 */
export function fetchKbList() {
  return request.get<Api.EverKB.KnowledgeBase[]>({
    url: '/api/kbs'
  })
}

/** 创建知识库 */
export function fetchCreateKb(params: Api.EverKB.KnowledgeBaseCreateParams) {
  return request.post<Api.EverKB.KnowledgeBase>({
    url: '/api/kbs',
    params
  })
}

/** 更新知识库（含启停） */
export function fetchUpdateKb(params: Api.EverKB.KnowledgeBaseUpdateParams) {
  return request.put<Api.EverKB.KnowledgeBase>({
    url: `/api/kbs/${params.id}`,
    params
  })
}

/** 删除知识库（仅空库可删） */
export function fetchDeleteKb(id: number) {
  return request.del<void>({
    url: `/api/kbs/${id}`
  })
}
