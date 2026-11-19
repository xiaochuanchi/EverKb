"""评测集合成脚本（二期 Task 28 Step 3）：真实 LLM 从评测库 chunk 反向抽 query。

手动执行（真实 LLM，不在 pytest 内）：
    python scripts/build_eval_set.py

流程：
1. 连 MySQL 读评测库（kb-eval-legal）的全部 chunk；
2. 随机抽样 ~50 个（seed=42 固定，可复现）；
3. 每个 chunk 让真实 LLM（豆包）反向抽 3 个白话 query；
4. 落盘 data/legal/eval_set.json（v1，含 version/seed/created_at）。

合成法 ground truth：relevant_chunk_ids = 该 chunk 自身（它必然能命中自己）。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.config import get_settings  # noqa: E402
from app.core.db import make_engine, make_session_factory  # noqa: E402
from app.evals import EvalSet, now_iso, save_eval_set  # noqa: E402
from app.models import Chunk, Document, KnowledgeBase  # noqa: E402
from app.services.llm import create_llm  # noqa: E402

EVAL_KB_NAME = "kb-eval-legal"
OUT_PATH = Path(__file__).resolve().parents[1] / "data" / "legal" / "eval_set.json"

SAMPLE_SIZE = 30
PER_CHUNK = 3
SEED = 42


def _main() -> int:
    settings = get_settings()
    engine = make_engine(settings.mysql_url)
    session_factory = make_session_factory(engine)
    llm = create_llm(settings)

    with session_factory() as session:
        kb = session.query(KnowledgeBase).filter(KnowledgeBase.name == EVAL_KB_NAME).first()
        if kb is None:
            print(f"评测库 {EVAL_KB_NAME} 不存在，请先跑 scripts/seed_eval_kb.py")
            return 1
        # chunk_id → doc_name 映射（供 EvalItem.doc_name）
        doc_names = dict(session.query(Document.id, Document.name).filter(Document.kb_id == kb.id))
        chunks = session.query(Chunk).filter(Chunk.kb_id == kb.id).all()
        print(f"评测库 {EVAL_KB_NAME}：{len(chunks)} chunk")

        chunk_tuples = [
            (c.id, c.content, doc_names.get(c.document_id, "")) for c in chunks
        ]

    print(f"抽样 {min(SAMPLE_SIZE, len(chunk_tuples))} 个 chunk × {PER_CHUNK} query，用真实 LLM 合成…")
    # 逐 chunk 合成（带进度），避免一次性 150 次调用无中间输出难定位卡点
    from app.evals import EvalItem, synthesize_queries
    import random
    rng = random.Random(SEED)
    sampled = rng.sample(chunk_tuples, k=min(SAMPLE_SIZE, len(chunk_tuples))) if chunk_tuples else []
    items: list[EvalItem] = []
    for i, (cid, text, dname) in enumerate(sampled, start=1):
        qs = synthesize_queries(text, llm, n=PER_CHUNK)
        for q in qs:
            items.append(EvalItem(query=q, relevant_chunk_ids=[cid], doc_name=dname))
        if i % 5 == 0 or i == len(sampled):
            print(f"  进度 {i}/{len(sampled)}（累计 {len(items)} 条）", flush=True)
    eval_set = EvalSet(version=1, seed=SEED, created_at=now_iso(), items=items)
    save_eval_set(eval_set, OUT_PATH)
    print(f"评测集已落盘：{OUT_PATH}（{len(items)} 条）")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
