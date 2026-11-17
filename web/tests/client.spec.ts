import axios, { AxiosError, type AxiosInstance, type AxiosResponse, type InternalAxiosRequestConfig } from "axios";
import { describe, expect, it, vi } from "vitest";

import { createApiClient } from "@/api/client";

/**
 * 出网红线在测试侧的落实：axios 实例注入 Fake 适配器，全程进程内，零真实请求。
 * 说明：自定义适配器不经过 axios 的 settle()，需手动套 validateStatus 语义，
 * 才能像真实网络栈一样把异常状态码 reject 成 AxiosError。
 */
function makeFakeInstance(handler: (config: InternalAxiosRequestConfig) => { status: number; data: unknown }): AxiosInstance {
  const instance = axios.create();
  instance.defaults.adapter = async (config: InternalAxiosRequestConfig): Promise<AxiosResponse> => {
    const { status, data } = handler(config);
    const response = { status, statusText: "", headers: {}, config, data } as AxiosResponse;
    if (!status || (config.validateStatus && !config.validateStatus(status))) {
      throw new AxiosError(
        `Request failed with status code ${status}`,
        AxiosError.ERR_BAD_REQUEST,
        config,
        undefined,
        response,
      );
    }
    return response;
  };
  return instance;
}

function authHeaderOf(config: InternalAxiosRequestConfig): string | undefined {
  // AxiosHeaderValue 含 null 等宽类型，此处仅在测试里关心字符串值
  return config.headers?.get("Authorization") as string | undefined;
}

describe("createApiClient：请求拦截", () => {
  it("getAccessToken 返回 token 时注入 Authorization: Bearer", async () => {
    let seen: string | undefined;
    const client = createApiClient(
      { getAccessToken: () => "t123", onUnauthorized: () => {} },
      makeFakeInstance((config) => {
        seen = authHeaderOf(config);
        return { status: 200, data: { code: 0, message: "ok", data: null } };
      }),
    );
    await client.get("/api/v1/ping");
    expect(seen).toBe("Bearer t123");
  });

  it("无 token 时不注入 Authorization 头", async () => {
    let seen: string | undefined;
    const client = createApiClient(
      { getAccessToken: () => null, onUnauthorized: () => {} },
      makeFakeInstance((config) => {
        seen = authHeaderOf(config);
        return { status: 200, data: { code: 0, message: "ok", data: null } };
      }),
    );
    await client.get("/api/v1/ping");
    expect(seen).toBeUndefined();
  });
});

describe("createApiClient：响应解包", () => {
  const opts = { getAccessToken: () => null, onUnauthorized: () => {} };

  it("成功信封直接解析为业务 data", async () => {
    const client = createApiClient(
      opts,
      makeFakeInstance(() => ({ status: 200, data: { code: 0, message: "ok", data: { list: [1, 2] } } })),
    );
    await expect(client.get("/api/v1/kbs")).resolves.toEqual({ list: [1, 2] });
  });

  it("业务错误（信封 code!=0）reject 出 ApiError", async () => {
    const client = createApiClient(
      opts,
      makeFakeInstance(() => ({ status: 409, data: { code: 409, message: "名称重复", data: null } })),
    );
    await expect(client.post("/api/v1/kbs", { name: "x" })).rejects.toMatchObject({
      name: "ApiError",
      code: 409,
      message: "名称重复",
    });
  });

  it("非信封错误体（网关 HTML）时用 HTTP 状态码兜底", async () => {
    const client = createApiClient(
      opts,
      makeFakeInstance(() => ({ status: 502, data: "<html>bad gateway</html>" })),
    );
    await expect(client.get("/api/v1/kbs")).rejects.toMatchObject({ code: 502 });
  });

  it("401 时先回调 onUnauthorized 再 reject", async () => {
    const onUnauthorized = vi.fn();
    const client = createApiClient(
      { getAccessToken: () => "expired", onUnauthorized },
      makeFakeInstance(() => ({ status: 401, data: { code: 401, message: "未登录", data: null } })),
    );
    await expect(client.get("/api/v1/kbs")).rejects.toMatchObject({ code: 401, message: "未登录" });
    expect(onUnauthorized).toHaveBeenCalledTimes(1);
  });

  it("网络层异常（无 HTTP 响应）折叠为 code=-1", async () => {
    const instance = axios.create();
    instance.defaults.adapter = (): Promise<AxiosResponse> => {
      throw new AxiosError("Network Error", "ECONNABORTED");
    };
    const client = createApiClient(opts, instance);
    await expect(client.get("/api/v1/kbs")).rejects.toMatchObject({ code: -1, message: "网络异常，请稍后重试" });
  });
});

describe("createApiClient：统一错误提示（借鉴 pengYanBPM 模式）", () => {
  const baseOpts = () => ({ getAccessToken: () => null, onUnauthorized: vi.fn() });

  it("业务错误回调 onBusinessError 一次（全局弹错的注入点）", async () => {
    const onBusinessError = vi.fn();
    const client = createApiClient(
      { ...baseOpts(), onBusinessError },
      makeFakeInstance(() => ({ status: 409, data: { code: 409, message: "名称重复", data: null } })),
    );
    await expect(client.post("/api/v1/kbs", { name: "x" })).rejects.toBeInstanceOf(Error);
    expect(onBusinessError).toHaveBeenCalledTimes(1);
    expect(onBusinessError.mock.calls[0][0]).toMatchObject({ code: 409, message: "名称重复" });
  });

  it("silent 请求失败不触发 onBusinessError，但错误仍 reject 给调用方", async () => {
    const onBusinessError = vi.fn();
    const client = createApiClient(
      { ...baseOpts(), onBusinessError },
      makeFakeInstance(() => ({ status: 404, data: { code: 404, message: "文档不存在", data: null } })),
    );
    await expect(client.get("/api/v1/docs/1", undefined, { silent: true })).rejects.toMatchObject({ code: 404 });
    expect(onBusinessError).not.toHaveBeenCalled();
  });

  it("网络层异常也回调 onBusinessError（统一提示覆盖网络错误）", async () => {
    const onBusinessError = vi.fn();
    const instance = axios.create();
    instance.defaults.adapter = (): Promise<AxiosResponse> => {
      throw new AxiosError("Network Error");
    };
    const client = createApiClient({ ...baseOpts(), onBusinessError }, instance);
    await expect(client.get("/api/v1/kbs")).rejects.toMatchObject({ code: -1 });
    expect(onBusinessError).toHaveBeenCalledTimes(1);
  });

  it("401 只走 onUnauthorized，不重复触发 onBusinessError", async () => {
    const onBusinessError = vi.fn();
    const onUnauthorized = vi.fn();
    const client = createApiClient(
      { getAccessToken: () => "expired", onUnauthorized, onBusinessError },
      makeFakeInstance(() => ({ status: 401, data: { code: 401, message: "未登录", data: null } })),
    );
    await expect(client.get("/api/v1/kbs")).rejects.toMatchObject({ code: 401 });
    expect(onUnauthorized).toHaveBeenCalledTimes(1);
    expect(onBusinessError).not.toHaveBeenCalled();
  });

  it("HTTP 200 但信封失败（防御路径）同样触发 onBusinessError", async () => {
    const onBusinessError = vi.fn();
    const client = createApiClient(
      { ...baseOpts(), onBusinessError },
      // 正常后端不该出现（失败恒 4xx/5xx），但解包层防御它
      makeFakeInstance(() => ({ status: 200, data: { code: 500, message: "服务器内部错误", data: null } })),
    );
    await expect(client.get("/api/v1/kbs")).rejects.toMatchObject({ code: 500, message: "服务器内部错误" });
    expect(onBusinessError).toHaveBeenCalledTimes(1);
  });
});
