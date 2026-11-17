import request from '@/utils/http'

/**
 * EverKB 文档管理 API
 * 管线状态机见类型定义 Api.EverKB.DocumentStatus
 */

/** 文档分页列表 */
export function fetchDocumentList(params: Api.EverKB.DocumentSearchParams) {
  return request.get<Api.Common.PaginatedResponse<Api.EverKB.Document>>({
    url: '/api/documents',
    params
  })
}

/** 上传文档（multipart/form-data） */
export function fetchUploadDocument(kbId: number, file: File) {
  const formData = new FormData()
  formData.append('file', file)
  return request.post<Api.EverKB.Document>({
    url: '/api/kbs/' + kbId + '/documents',
    data: formData,
    timeout: 120000
  })
}

/** 批量导入网页 URL */
export function fetchImportUrls(params: Api.EverKB.DocumentImportUrlsParams) {
  return request.post<Api.EverKB.Document[]>({
    url: '/api/documents/import-urls',
    params
  })
}

/** 替换重传（version+1，走完整管线，成功后按旧 ids 清旧向量） */
export function fetchReplaceDocument(id: number, file: File) {
  const formData = new FormData()
  formData.append('file', file)
  return request.post<Api.EverKB.Document>({
    url: `/api/documents/${id}/replace`,
    data: formData,
    timeout: 120000
  })
}

/** 失败重试（开头清理残留 chunk 后从头执行） */
export function fetchRetryDocument(id: number) {
  return request.post<Api.EverKB.Document>({
    url: `/api/documents/${id}/retry`
  })
}

/** 启用/停用（Milvus enabled 标志翻转 + MySQL 同步） */
export function fetchToggleDocument(id: number, enabled: boolean) {
  return request.put<Api.EverKB.Document>({
    url: `/api/documents/${id}/enabled`,
    params: { enabled }
  })
}

/**
 * 删除（顺序硬约束：Milvus → MySQL → 存储层）
 * 删除顺序由后端保证，前端仅发起
 */
export function fetchDeleteDocument(id: number) {
  return request.del<void>({
    url: `/api/documents/${id}`
  })
}

/** 获取 content.md（内容真相，可编辑） */
export function fetchDocumentContent(id: number) {
  return request.get<string>({
    url: `/api/documents/${id}/content`
  })
}

/** 保存 content.md（edited=true，跳过解析重跑切块→向量化） */
export function fetchSaveDocumentContent(id: number, content: string) {
  return request.put<Api.EverKB.Document>({
    url: `/api/documents/${id}/content`,
    params: { content }
  })
}

/** 原始文件签名下载链接 */
export function fetchDocumentSourceUrl(id: number) {
  return request.get<string>({
    url: `/api/documents/${id}/source-url`
  })
}
