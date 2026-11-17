/**
 * EverKB API 接口类型定义
 *
 * 对齐设计文档《2026-11-14-rag知识库管理平台-设计文档.md》§5 数据模型
 * 与 §6.1 文档状态机。后端 API 就绪前作为前端契约先行定义。
 *
 * @module types/api/everkb
 */

declare namespace Api {
  namespace EverKB {
    /* ============ 枚举与常量 ============ */

    /** 知识库/文档 启用状态 */
    enum EnabledStatus {
      Disabled = 0,
      Enabled = 1
    }

    /**
     * 文档处理状态机（设计文档 §6.1）
     * 已上传(1) → 解析中(2) → 已提取(3) → 已切块(4) → 向量化中(5) → 已完成(6)
     *                                ↘ 任一环节失败 → 失败(7)
     */
    enum DocumentStatus {
      Uploaded = 1,
      Parsing = 2,
      Extracted = 3,
      Chunked = 4,
      Vectorizing = 5,
      Completed = 6,
      Failed = 7
    }

    /** 文档来源类型 */
    enum SourceType {
      Upload = 1,
      WebPage = 2
    }

    /** 用户反馈：0 未反馈 / 1 满意 / -1 不满意 */
    enum Feedback {
      Negative = -1,
      None = 0,
      Positive = 1
    }

    /**
     * Span 类型（对齐 OpenTelemetry GenAI 语义规范）
     * tool / agent_step 为二期预留，界面按任意深度子树渲染
     */
    enum SpanType {
      Embedding = 'embedding',
      Retrieval = 'retrieval',
      Db = 'db',
      Llm = 'llm',
      Tool = 'tool',
      AgentStep = 'agent_step'
    }

    /* ============ 知识库 ============ */

    interface KnowledgeBase {
      id: number
      name: string
      description: string
      status: EnabledStatus
      createdAt: string
      updatedAt: string
    }

    interface KnowledgeBaseCreateParams {
      name: string
      description?: string
    }

    interface KnowledgeBaseUpdateParams extends KnowledgeBaseCreateParams {
      id: number
      status?: EnabledStatus
    }

    /* ============ 应用（产品侧机器人/场景） ============ */

    interface App {
      id: number
      name: string
      kbIds: number[]
      topK: number
      scoreThreshold: number
      promptTemplate: string
      modelParams: {
        baseUrl?: string
        apiKey?: string
        model?: string
        [key: string]: unknown
      }
      createdAt: string
      updatedAt: string
    }

    interface AppCreateParams {
      name: string
      kbIds: number[]
      topK?: number
      scoreThreshold?: number
      promptTemplate?: string
      modelParams?: App['modelParams']
    }

    interface AppUpdateParams extends AppCreateParams {
      id: number
    }

    /* ============ 文档 ============ */

    interface Document {
      id: number
      kbId: number
      name: string
      sourceType: SourceType
      ossKey: string
      sourceUrl?: string
      fileType: string
      fileSize: number
      status: DocumentStatus
      statusReason?: string
      version: number
      enabled: boolean
      chunkCount: number
      edited: boolean
      uploadedBy: string
      createdAt: string
      updatedAt: string
    }

    interface DocumentSearchParams {
      kbId?: number
      keyword?: string
      status?: DocumentStatus
      current?: number
      size?: number
    }

    /** 批量导入网页 URL */
    interface DocumentImportUrlsParams {
      kbId: number
      urls: string[]
    }

    /* ============ Chunk ============ */

    interface Chunk {
      id: number
      documentId: number
      kbId: number
      chunkIndex: number
      pageNumber?: number
      content: string
      tokenCount: number
      vectorized: boolean
      createdAt: string
    }

    interface ChunkSearchParams {
      documentId?: number
      kbId?: number
      vectorized?: boolean
      current?: number
      size?: number
    }

    /* ============ 问答记录（= 一条 Trace 的主表） ============ */

    interface QaRecord {
      id: number
      appId: number
      userKey: string
      sessionId?: string
      question: string
      answer: string
      /** FALSE = 零命中自由发挥（未基于知识库） */
      grounded: boolean
      chunkIds: number[]
      docIds: number[]
      scores: number[]
      latencyMs: number
      totalCost?: number
      feedback: Feedback
      createdAt: string
    }

    interface QaRecordSearchParams {
      appId?: number
      feedback?: Feedback
      grounded?: boolean
      keyword?: string
      current?: number
      size?: number
    }

    /** 引用详情（聊天接口下发结构） */
    interface Citation {
      docName: string
      docId: number
      chunkId: number
      pageNumber?: number
      snippet: string
      score: number
      sourceUrl?: string
    }

    /* ============ Trace / Span ============ */

    /**
     * 链路步骤（树结构，parentSpanId 构成树）
     * traceId = qaRecord.id
     */
    interface TraceSpan {
      id: number
      traceId: number
      parentSpanId?: number
      /** 如 gen_ai.embedding / milvus.search / gen_ai.chat */
      name: string
      spanType: SpanType
      inputSummary?: string
      outputSummary?: string
      latencyMs: number
      genAiUsageTokensIn?: number
      genAiUsageTokensOut?: number
      cost?: number
      extra?: Record<string, unknown>
      createdAt: string
    }

    interface TraceSearchParams {
      appId?: number
      minLatencyMs?: number
      keyword?: string
      current?: number
      size?: number
    }

    /** Trace 聚合指标（跨 Trace 分析页） */
    interface TraceAggregation {
      /** 最慢调用 Top N */
      slowestTraces: Array<{
        traceId: number
        question: string
        latencyMs: number
        totalCost?: number
      }>
      /** 各步骤 P95 延迟（毫秒） */
      stepP95: Array<{
        spanType: SpanType
        p95LatencyMs: number
      }>
    }

    /* ============ 对账工具 ============ */

    /** 漂移扫描结果 */
    interface ReconcileReport {
      /** MySQL 有 vectorized=true 但 Milvus 缺失 */
      mysqlOnly: number
      /** Milvus 有但 MySQL 已删/停用 */
      milvusOnly: number
      /** 需要重建的 chunk ids */
      chunkIdsToRebuild: number[]
      scannedAt: string
    }
  }
}
