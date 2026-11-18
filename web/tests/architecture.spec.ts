import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * 架构边界测试（排期文档 §6 风险 3）：
 * chat-kit 与门户壳解耦是第一天的约束，用可执行测试固化，
 * 后续若引入 ESLint 再叠加 import 规则（双保险）。
 *
 * F3（Task 31）chat-kit 已落地：sse.ts / store.ts / ChatKit.vue / types.ts / index.ts。
 * 本测试递归扫描 chat-kit 目录下全部 .ts/.vue，锁死三类越界：
 * 1. 门户壳模块（router/views/stores/layouts/api 单例）；
 * 2. element-plus（embed 独立打包）；
 * 3. axios（SSE 走原生 fetch，不进统一信封拦截器）。
 */
const KIT_DIR = join(__dirname, "..", "src", "chat-kit");
/** 门户壳专属模块：chat-kit 引用它们 = 反向耦合，embed widget 场景被打穿 */
const FORBIDDEN = /["']@\/(router|views|stores|layouts|api\/index)/;
/** chat-kit 内禁止出现 element-plus（embed widget 需独立轻量打包） */
const FORBIDDEN_PKG = /from\s+["']element-plus/;
/** chat-kit 内禁止 import axios（流式走 sse.ts 原生 fetch） */
const FORBIDDEN_AXIOS = /from\s+["']axios/;

function collectCodeFiles(dir: string): string[] {
  const out: string[] = [];
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) {
      out.push(...collectCodeFiles(full));
    } else if (/\.(ts|vue)$/.test(name)) {
      out.push(full);
    }
  }
  return out;
}

describe("chat-kit 架构边界", () => {
  it("禁止引用门户壳模块（router / views / stores / layouts / api 单例）", () => {
    const offenders: string[] = [];
    for (const file of collectCodeFiles(KIT_DIR)) {
      const content = readFileSync(file, "utf8");
      if (FORBIDDEN.test(content)) {
        offenders.push(file);
      }
    }
    expect(offenders, `以下文件越界引用门户壳模块：\n${offenders.join("\n")}`).toEqual([]);
  });

  it("禁止依赖 element-plus（embed widget 独立打包约束）", () => {
    const offenders: string[] = [];
    for (const file of collectCodeFiles(KIT_DIR)) {
      const content = readFileSync(file, "utf8");
      if (FORBIDDEN_PKG.test(content)) {
        offenders.push(file);
      }
    }
    expect(offenders).toEqual([]);
  });

  it("禁止依赖 axios（流式走原生 fetch，不进统一信封拦截器）", () => {
    const offenders: string[] = [];
    for (const file of collectCodeFiles(KIT_DIR)) {
      const content = readFileSync(file, "utf8");
      if (FORBIDDEN_AXIOS.test(content)) {
        offenders.push(file);
      }
    }
    expect(offenders).toEqual([]);
  });
});
