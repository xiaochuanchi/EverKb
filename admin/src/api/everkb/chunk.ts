import request from '@/utils/http'

/**
 * EverKB Chunk API
 * chunk 内容来自 content.md，双存 MySQL 与 Milvus（id 兼作 Milvus 主键）
 */

/** chunk 分页列表 */
export function fetchChunkList(params: Api.EverKB.ChunkSearchParams) {
  return request.get<Api.Common.PaginatedResponse<Api.EverKB.Chunk>>({
    url: '/api/chunks',
    params
  })
}

/** 单文档 chunk 全量（按 chunk_index 排序） */
export function fetchDocumentChunks(documentId: number) {
  return request.get<Api.EverKB.Chunk[]>({
    url: `/api/documents/${documentId}/chunks`
  })
}
