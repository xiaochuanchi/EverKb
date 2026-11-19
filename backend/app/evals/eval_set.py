"""评测集数据契约与落盘（二期 Task 27）：版本化 ground truth，重跑可复现。

ground truth 来源两段式（计划文档 Global Constraints）：
- 合成法为主：从已入库 chunk 反向抽 query，`relevant_chunk_ids` = 该 chunk 自身；
- 人工抽验 10% 修正后 bump 版本。

落盘为 `data/legal/eval_set.json`，含 version / seed / created_at 元信息，
保证「同一评测集 + 同一检索器 → 两次跑分一致」（可复现红线）。
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class EvalItem:
    """一条评测样本：query + 应命中的 chunk 集合 + 来源文档。"""

    query: str
    relevant_chunk_ids: list[int]   # ground truth：应命中的 chunk id
    doc_name: str

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "EvalItem":
        return cls(
            query=data["query"],
            relevant_chunk_ids=[int(c) for c in data["relevant_chunk_ids"]],
            doc_name=data["doc_name"],
        )


@dataclass
class EvalSet:
    """一份评测集：样本列表 + 版本元信息。"""

    version: int
    seed: int
    created_at: str
    items: list[EvalItem]

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "seed": self.seed,
            "created_at": self.created_at,
            "items": [it.to_dict() for it in self.items],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "EvalSet":
        return cls(
            version=int(data["version"]),
            seed=int(data["seed"]),
            created_at=data["created_at"],
            items=[EvalItem.from_dict(it) for it in data["items"]],
        )


def save_eval_set(eval_set: EvalSet, path: str | Path) -> None:
    """落盘评测集（含版本元信息）。UTF-8，ensure_ascii=False 保留中文可读。"""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(
        json.dumps(eval_set.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_eval_set(path: str | Path) -> EvalSet:
    """读取评测集；文件缺失或结构非法抛异常（不静默降级）。"""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return EvalSet.from_dict(data)


def now_iso() -> str:
    """当前 UTC 时间的 ISO 字符串，落盘时间戳。"""
    return datetime.now(timezone.utc).isoformat()
