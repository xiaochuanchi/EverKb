/** 后端统一信封形状（契约：docs/2026-11-17-api统一信封-设计文档.md）。 */
export interface ApiEnvelope<T = unknown> {
  code: number;
  message: string;
  data: T | null;
}

/**
 * 前端统一业务异常。
 * code 语义：成功恒 0；失败 = HTTP 状态码；网络层 / 信封格式异常用 -1（服务端不会产生该值）。
 */
export class ApiError extends Error {
  readonly code: number;
  /** 422 时为校验明细数组（loc/msg/type），其余场景通常为 null */
  readonly data: unknown;

  constructor(code: number, message: string, data: unknown = null) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.data = data;
  }
}

/** 扩展 axios 配置：静默标记（借鉴 pengYanBPM 统一提示模式的增强项）。 */
declare module "axios" {
  export interface AxiosRequestConfig {
    /**
     * 静默请求：失败不触发全局错误提示（onBusinessError），
     * 由调用方自行处理（如状态轮询里 404 应静默）。
     */
    silent?: boolean;
  }
}
