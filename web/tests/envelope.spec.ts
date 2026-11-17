import { describe, expect, it } from "vitest";

import { httpErrorToApiError, networkErrorToApiError, unwrapEnvelope } from "@/api/envelope";
import { ApiError } from "@/api/types";

describe("unwrapEnvelope：成功信封", () => {
  it("code=0 返回 data 原样（含分页结构不摊平）", () => {
    const data = { items: [{ id: 1 }], total: 1 };
    expect(unwrapEnvelope({ code: 0, message: "ok", data })).toBe(data);
  });

  it("code=0 且 data 为 null（如删除端点 204→200）时返回 null", () => {
    expect(unwrapEnvelope({ code: 0, message: "ok", data: null })).toBeNull();
  });
});

describe("unwrapEnvelope：失败信封", () => {
  it("业务错误抛 ApiError，code/message/data 透传", () => {
    try {
      unwrapEnvelope({ code: 409, message: "知识库不存在", data: null });
      expect.unreachable("应当抛出 ApiError");
    } catch (e) {
      const err = e as ApiError;
      expect(err).toBeInstanceOf(ApiError);
      expect(err.code).toBe(409);
      expect(err.message).toBe("知识库不存在");
      expect(err.data).toBeNull();
    }
  });

  it("422 校验失败时明细数组保留在 data", () => {
    const details = [{ loc: ["body", "name"], msg: "Field required", type: "missing" }];
    try {
      unwrapEnvelope({ code: 422, message: "参数校验失败", data: details });
      expect.unreachable("应当抛出 ApiError");
    } catch (e) {
      expect((e as ApiError).data).toEqual(details);
    }
  });

  it("code 非 0 且 message 缺失时生成兜底文案", () => {
    // 非标准信封但 code 是数字：按失败处理而不是误判成功
    try {
      unwrapEnvelope({ code: 500 });
      expect.unreachable("应当抛出 ApiError");
    } catch (e) {
      expect((e as ApiError).message).toContain("500");
    }
  });

  it("响应体不是信封（如网关 HTML 错误页）时抛格式异常，绝不放行为成功", () => {
    for (const bad of ["<html>502</html>", null, undefined, { status: "ok" }, [1, 2]]) {
      try {
        unwrapEnvelope(bad);
        expect.unreachable(`应当抛出 ApiError：${String(bad)}`);
      } catch (e) {
        expect((e as ApiError).code).toBe(-1);
      }
    }
  });
});

describe("httpErrorToApiError：HTTP 层错误映射", () => {
  it("错误响应是信封时取信封的 code 与 message", () => {
    const err = httpErrorToApiError(404, { code: 404, message: "文档不存在", data: null });
    expect(err.code).toBe(404);
    expect(err.message).toBe("文档不存在");
  });

  it("错误响应不是信封（网关页）时用 HTTP 状态码兜底", () => {
    const err = httpErrorToApiError(502, "Bad Gateway");
    expect(err.code).toBe(502);
    expect(err.message).toContain("502");
  });
});

describe("networkErrorToApiError", () => {
  it("网络异常统一 code=-1 与固定文案", () => {
    const err = networkErrorToApiError();
    expect(err.code).toBe(-1);
    expect(err.message).toBe("网络异常，请稍后重试");
  });
});
