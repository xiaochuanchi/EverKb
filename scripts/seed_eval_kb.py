"""评测库入库脚本（二期 Task 26）：建 kb-eval-legal 库，传 12 部法规，处理到完成。

手动执行（真实网络 + 真实中间件，不在 pytest 内）：
    python scripts/seed_eval_kb.py

流程：
1. 连真实 MySQL（settings.mysql_url）+ Milvus（create_vector）+ Embedder（create_embedder）；
2. 建/复用知识库「kb-eval-legal」（评测与演示库隔离，红线）；
3. 逐个读 data/legal/*.md → 建 Document 行 → 写 source 对象 → process_document 处理；
4. 统计总 chunk 数（应落在 180–260 区间，决策文档 §6.5 预估）。

说明：评测库可反复清空重建——删除顺序红线 3（Milvus 向量 → MySQL chunk → doc → 存储）。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.config import get_settings  # noqa: E402
from app.core.db import make_engine, make_session_factory  # noqa: E402
from app.core.storage import LocalDiskStorage  # noqa: E402
from app.models import Chunk, Document, DocumentStatus, KnowledgeBase, SourceType  # noqa: E402
from app.services.embedding import create_embedder  # noqa: E402
from app.services.pipeline import process_document  # noqa: E402
from app.services.vector import create_vector  # noqa: E402

EVAL_KB_NAME = "kb-eval-legal"
LEGAL_DIR = Path(__file__).resolve().parents[1] / "data" / "legal"


def _main() -> int:
    settings = get_settings()
    engine = make_engine(settings.mysql_url)
    session_factory = make_session_factory(engine)
    storage = LocalDiskStorage(root=settings.storage_root)
    embedder = create_embedder(settings)
    vector = create_vector(settings)
    vector.ensure_collection()

    with session_factory() as session:
        # 建/复用评测库
        kb = session.query(KnowledgeBase).filter(KnowledgeBase.name == EVAL_KB_NAME).first()
        if kb is None:
            kb = KnowledgeBase(name=EVAL_KB_NAME, description="二期检索评测专用库（法律·网络安全与数据合规法规包）")
            session.add(kb)
            session.commit()
            session.refresh(kb)
            print(f"[建库] {EVAL_KB_NAME} (id={kb.id})")
        else:
            print(f"[复用] {EVAL_KB_NAME} (id={kb.id})")

        kb_id = kb.id
        md_files = sorted(LEGAL_DIR.glob("*.md"))
        total_chunks = 0

        for md_path in md_files:
            name = md_path.stem
            md_text = md_path.read_text(encoding="utf-8")
            # 同名文档已存在且完成 → 跳过（幂等重跑）
            existing = session.query(Document).filter(
                Document.kb_id == kb_id, Document.name == name
            ).first()
            if existing is not None and existing.status == DocumentStatus.COMPLETED:
                print(f"[跳过] {name}（已完成）")
                total_chunks += existing.chunk_count
                continue

            doc = Document(
                kb_id=kb_id,
                name=name,
                source_type=SourceType.UPLOAD,
                file_type="md",
                file_size=len(md_text.encode("utf-8")),
                status=DocumentStatus.UPLOADED,
            )
            session.add(doc)
            session.flush()
            doc.oss_key = f"kb/{kb_id}/doc/{doc.id}/source.md"
            storage.put_bytes(doc.oss_key, md_text.encode("utf-8"))
            session.commit()

            process_document(
                session, doc.id,
                storage=storage, embedder=embedder, vector=vector, settings=settings,
            )
            session.refresh(doc)
            if doc.status != DocumentStatus.COMPLETED:
                print(f"[失败] {name} → status={doc.status} reason={doc.status_reason}")
            else:
                print(f"[完成] {name} → {doc.chunk_count} chunk")
            total_chunks += doc.chunk_count

    print(f"\n总 chunk 数：{total_chunks}（预估甜点区 180–260）")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
