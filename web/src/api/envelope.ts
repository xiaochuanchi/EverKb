import { ApiError, type ApiEnvelope } from "./types";

/** 判断响应体是否形如统一信封（存在数字 code 即认为有信封头）。 */
function isEnvelope(body: unknown): body is ApiEnvelope {
  return (
    typeof body === "object" &&
    body !== null &&
    typeof (body as ApiEnvelope).code === "number"
  );
}

/**
 * 解包成功响应的信封：code === 0 返回 data。
 * 业务失败（code !== 0）或响应体不是信封时抛 ApiError。
 */
export function unwrapEnvelope(body: unknown): unknown {
  if (!isEnvelope(body)) {
    // 兜底场景：网关 502/504 返回 HTML、代理误配等——绝不把未知形状当成功处理
    throw new ApiError(-1, "响应格式异常：不是有效的统一信封");
  }
  if (body.code !== 0) {
    throw new ApiError(
      body.code,
      body.message || `请求失败（code ${body.code}）`,
      body.data ?? null,
    );
  }
  return body.data;
}

/**
 * HTTP 层错误（4xx/5xx 已被 axios reject）统一映射为 ApiError。
 * 后端异常处理器保证错误响应也是信封，此处对非信封体（如网关错误页）做兜底。
 */
export function httpErrorToApiError(status: number, body: unknown): ApiError {
  if (isEnvelope(body)) {
    return new ApiError(
      body.code ?? status,
      body.message || `请求失败（HTTP ${status}）`,
      body.data ?? null,
    );
  }
  return new ApiError(status, `请求失败（HTTP ${status}）`);
}

/** 网络层异常（断网 / 超时 / 代理不可达，无 HTTP 响应）的统一映射。 */
export function networkErrorToApiError(): ApiError {
  return new ApiError(-1, "网络异常，请稍后重试");
}
