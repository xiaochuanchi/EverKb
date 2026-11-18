import request from '@/utils/http'

/**
 * 知识库管理 API（对齐后端 /api/v1/admin/kbs）
 */

/** 知识库列表（GET /kbs，后端不分页，按 id 升序） */
export function fetchKbList() {
  return request.get<Api.EverKB.KB[]>({
    url: '/api/v1/admin/kbs'
  })
}

/** 创建知识库（重名 409） */
export function createKb(data: Api.EverKB.KBCreateParams) {
  return request.post<Api.EverKB.KB>({
    url: '/api/v1/admin/kbs',
    params: data,
    showSuccessMessage: true
  })
}

/** 局部更新（name/description/status） */
export function updateKb(id: number, data: Api.EverKB.KBPatchParams) {
  return request.request<Api.EverKB.KB>({
    url: `/api/v1/admin/kbs/${id}`,
    method: 'PATCH',
    data,
    showSuccessMessage: true
  })
}

/** 删除知识库（仅空库可删，非空 409） */
export function deleteKb(id: number) {
  return request.del<null>({
    url: `/api/v1/admin/kbs/${id}`,
    showSuccessMessage: true
  })
}
