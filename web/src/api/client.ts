import axios, {
  AxiosError,
  type AxiosInstance,
  type AxiosResponse,
  type InternalAxiosRequestConfig,
} from "axios";

import { httpErrorToApiError, networkErrorToApiError, unwrapEnvelope } from "./envelope";
import { ApiError } from "./types";

/** 客户端依赖缝：token 获取、401 处置、错误提示均由调用方注入，client.ts 不依赖 pinia / router / element-plus。 */
export interface ApiClientOptions {
  getAccessToken: () => string | null;
  /** 收到 HTTP 401 时回调（如：清 token + 弹重新登录对话）。重复弹窗由调用方去重（见 api/index.ts）。 */
  onUnauthorized: (err: ApiError) => void;
  /**
   * 业务 / HTTP / 网络错误的统一提示回调（如弹 ElMessage.error）。
   * silent 请求不回调（借鉴 pengYanBPM 全局 Message 模式，追加静默逃生口）。
   */
  onBusinessError?: (err: ApiError) => void;
}

/** 单次请求的可选项。 */
export interface RequestOptions {
  /** 失败不触发全局错误提示，由调用方自行处理（如状态轮询里的非致命错误） */
  silent?: boolean;
}

/** 应用侧使用的轻封装：拦截器已把信封解包为业务 data，直接拿到强类型结果。 */
export interface ApiClient {
  get<T>(url: string, params?: Record<string, unknown>, opts?: RequestOptions): Promise<T>;
  post<T>(url: string, body?: unknown, opts?: RequestOptions): Promise<T>;
  patch<T>(url: string, body?: unknown, opts?: RequestOptions): Promise<T>;
  put<T>(url: string, body?: unknown, opts?: RequestOptions): Promise<T>;
  delete<T>(url: string, opts?: RequestOptions): Promise<T>;
}

/**
 * 创建 API 客户端：
 * - 请求拦截：注入 Bearer token；
 * - 响应拦截：成功解信封返回 data，失败折叠为 ApiError；
 * - 错误提示：非 401 失败回调 onBusinessError（统一弹错），silent 请求除外；
 * - 401：单独走 onUnauthorized（重新登录对话由它负责，不重复弹普通错误）。
 * 注意：SSE 流式接口（F3 问答）不走本客户端，用原生 fetch（见排期文档技术栈表）。
 */
export function createApiClient(
  options: ApiClientOptions,
  instance: AxiosInstance = axios.create({ timeout: 30_000 }),
): ApiClient {
  instance.interceptors.request.use((config: InternalAxiosRequestConfig) => {
    const token = options.getAccessToken();
    if (token) {
      config.headers.set("Authorization", `Bearer ${token}`);
    }
    return config;
  });

  instance.interceptors.response.use(
    // 运行时语义：把 AxiosResponse 替换为解包后的业务 data；断言只为通过拦截器签名。
    // 防御路径：HTTP 200 但信封 code != 0（正常不该出现，后端方案失败即 4xx/5xx），
    // 同样折叠为 ApiError 并走统一提示。
    (response: AxiosResponse): AxiosResponse => {
      try {
        return unwrapEnvelope(response.data) as unknown as AxiosResponse;
      } catch (e) {
        if (e instanceof ApiError && !response.config.silent) {
          options.onBusinessError?.(e);
        }
        throw e;
      }
    },
    (error: unknown) => {
      if (error instanceof AxiosError) {
        if (error.response) {
          const apiErr = httpErrorToApiError(error.response.status, error.response.data);
          if (error.response.status === 401) {
            options.onUnauthorized(apiErr);
          } else if (!error.config?.silent) {
            options.onBusinessError?.(apiErr);
          }
          return Promise.reject(apiErr);
        }
        const netErr = networkErrorToApiError();
        if (!error.config?.silent) {
          options.onBusinessError?.(netErr);
        }
        return Promise.reject(netErr);
      }
      return Promise.reject(error);
    },
  );

  // 拦截器已在运行时把响应替换为业务 data，此处的双重断言只为对齐 TS 类型
  const unwrap = <T>(p: Promise<unknown>): Promise<T> =>
    p as unknown as Promise<T>;

  return {
    get: (url, params, opts) =>
      unwrap(instance.get(url, { params, silent: opts?.silent })),
    post: (url, body, opts) => unwrap(instance.post(url, body, { silent: opts?.silent })),
    patch: (url, body, opts) => unwrap(instance.patch(url, body, { silent: opts?.silent })),
    put: (url, body, opts) => unwrap(instance.put(url, body, { silent: opts?.silent })),
    delete: (url, opts) => unwrap(instance.delete(url, { silent: opts?.silent })),
  };
}
