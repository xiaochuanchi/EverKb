"""评测集合成（二期 Task 27）：从 chunk 反向抽 query，LLM 白话化改写。

合成法 ground truth 假设：给定一个 chunk，让 LLM 生成「用户会怎么问」的
白话 query，`relevant_chunk_ids` 即该 chunk 自身（它必然能命中自己）。

纪律：
- LLM 生成是离线数据准备（真实 LLM），但不在 pytest 内跑——测试注入 FakeLLM
  锁 `synthesize_queries` 的输入输出契约；
- 随机抽样用固定 seed，保证可复现；
- 每 chunk 生成 n 个 query，避免单一 query 的偶然性。
"""
from __future__ import annotations

import random

from app.services.llm.base import ChatMessage, LLMClient

# 合成 Prompt：让 LLM 把法条原文改写成「用户会怎么问」的白话问题
_SYNTH_PROMPT = (
    "以下是法律条文片段。请生成 {n} 个用户可能提出的问题（用口语化、白话来问），"
    "每个问题单独一行，不要编号，不要解释。\n\n条文：\n{chunk_text}"
)


def synthesize_queries(chunk_text: str, llm: LLMClient, *, n: int = 3) -> list[str]:
    """给定一个 chunk，让 LLM 生成 n 个白话 query。

    返回按行拆分的非空 query 列表；若 LLM 返回行数不足 n，按实际返回。
    """
    prompt = _SYNTH_PROMPT.format(n=n, chunk_text=chunk_text)
    result = llm.chat([ChatMessage(role="user", content=prompt)], temperature=0.7)
    lines = [ln.strip() for ln in result.content.splitlines() if ln.strip()]
    # 去掉 LLM 可能误加的编号前缀（如 "1. " / "1、"）
    cleaned = [_strip_leading_number(ln) for ln in lines]
    return cleaned[:n]


def build_eval_set(
    chunks: list[tuple[int, str, str]],  # (chunk_id, chunk_text, doc_name)
    llm: LLMClient,
    *,
    sample_size: int = 50,
    per_chunk: int = 3,
    seed: int = 42,
) -> list[EvalItem]:
    """从 chunks 随机抽样 sample_size 个，每个反向抽 per_chunk 个 query。

    返回 EvalItem 列表（query 与 chunk 一一对应，relevant_chunk_ids=[chunk_id]）。
    抽样用固定 seed 保证可复现。
    """
    from app.evals.eval_set import EvalItem

    rng = random.Random(seed)
    sampled = rng.sample(chunks, k=min(sample_size, len(chunks))) if chunks else []
    items: list[EvalItem] = []
    for chunk_id, chunk_text, doc_name in sampled:
        queries = synthesize_queries(chunk_text, llm, n=per_chunk)
        for q in queries:
            items.append(EvalItem(
                query=q,
                relevant_chunk_ids=[chunk_id],
                doc_name=doc_name,
            ))
    return items


def _strip_leading_number(line: str) -> str:
    """去掉 LLM 误加的编号前缀（如 "1. " / "1、" / "1)"）。"""
    import re

    return re.sub(r"^\s*\d+\s*[.、)）]\s*", "", line).strip()
