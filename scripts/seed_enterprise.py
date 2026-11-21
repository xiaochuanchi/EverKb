"""开箱体验播种脚本（M4）：给企业播种示例知识库 + 预配置应用。

设计出处《商业化多租户设计方案 2026-11-20》§8：开通即开箱可用——第一分钟
能提问比额度数字更决定转化。种子内容做成资源包目录（--seed-dir 指向可替换
的资料夹），不同行业可换不同包。

用法（仓库根）：
    .venv/bin/python scripts/seed_enterprise.py --enterprise-id 1
    .venv/bin/python scripts/seed_enterprise.py --enterprise-id 1 --seed-dir data/seed

行为（幂等可重跑）：
- 示例知识库：按固定命名规则「示例知识库-<enterprise_id>」查找，存在即复用；
- 示例文档：同名文档已完成则跳过，失败/未完成则重建重跑；
- 预配置应用：按固定命名「示例助手-<enterprise_id>」查找，存在即复用；
  不存在才创建（挂示例 KB、dense 检索、top_k=5、默认 prompt 模板、生成 api_key）。

说明：脚本连真实 MySQL + Milvus + Embedder（同 seed_eval_kb.py 先例），不在
pytest 内跑；播种幂等性由 test_seed_enterprise.py 用 SQLite + Fake 依赖锁定。
"""
import argparse
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from sqlalchemy import select  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.db import make_engine, make_session_factory  # noqa: E402
from app.core.storage import LocalDiskStorage  # noqa: E402
from app.models import (  # noqa: E402
    App,
    Document,
    DocumentStatus,
    Enterprise,
    KnowledgeBase,
    SourceType,
)
from app.services.embedding import create_embedder  # noqa: E402
from app.services.pipeline import process_document  # noqa: E402
from app.services.vector import create_vector  # noqa: E402

_API_KEY_PREFIX = "sk-"
_DEFAULT_SEED_DIR = Path(__file__).resolve().parents[1] / "data" / "seed"


def _generate_api_key() -> str:
    """生成 X-API-Key：sk- + 48 位十六进制随机（对齐 apps.py._generate_api_key）。"""
    return f"{_API_KEY_PREFIX}{secrets.token_hex(24)}"


def _kb_name(enterprise_id: int) -> str:
    return f"示例知识库-{enterprise_id}"


def _app_name(enterprise_id: int) -> str:
    return f"示例助手-{enterprise_id}"


def seed_enterprise(
    session_factory,
    *,
    enterprise_id: int,
    seed_dir: Path,
    storage,
    embedder,
    vector,
    settings,
    tracer=None,
    bm25=None,
) -> dict:
    """给企业播种示例 KB + 预配置应用。幂等：已存在则复用。

    返回 dict：{"kb_id": int, "doc_count": int, "app_id": int|None, "app_created": bool}
    """
    with session_factory() as session:
        ent = session.get(Enterprise, enterprise_id)
        if ent is None:
            raise ValueError(f"企业不存在：id={enterprise_id}")

        # 1) 示例知识库（复用或新建）
        kb = session.scalar(
            select(KnowledgeBase).where(KnowledgeBase.name == _kb_name(enterprise_id))
        )
        if kb is None:
            kb = KnowledgeBase(
                name=_kb_name(enterprise_id),
                description="开箱示例知识库（可删除，不影响正常使用）",
                enterprise_id=enterprise_id,
            )
            session.add(kb)
            session.commit()
            session.refresh(kb)

        # 2) 种子文档逐个入库（同名已完成则跳过）
        doc_count = 0
        for md_path in sorted(seed_dir.glob("*.md")):
            name = md_path.stem
            md_text = md_path.read_text(encoding="utf-8")
            existing = session.scalar(
                select(Document).where(
                    Document.kb_id == kb.id, Document.name == name
                )
            )
            if existing is not None and existing.status == DocumentStatus.COMPLETED:
                doc_count += 1
                continue

            doc = Document(
                kb_id=kb.id,
                enterprise_id=enterprise_id,
                name=name,
                source_type=SourceType.UPLOAD,
                file_type="md",
                file_size=len(md_text.encode("utf-8")),
                status=DocumentStatus.UPLOADED,
            )
            session.add(doc)
            session.flush()
            doc.oss_key = f"kb/{kb.id}/doc/{doc.id}/source.md"
            storage.put_bytes(doc.oss_key, md_text.encode("utf-8"))
            session.commit()

            process_document(
                session, doc.id,
                storage=storage, embedder=embedder, vector=vector, settings=settings,
                tracer=tracer, bm25=bm25,
            )
            session.refresh(doc)
            if doc.status != DocumentStatus.COMPLETED:
                print(f"  [失败] {name} → status={doc.status} reason={doc.status_reason}")
            else:
                print(f"  [完成] {name} → {doc.chunk_count} chunk")
            doc_count += 1

        # 3) 预配置应用（复用或新建）
        app = session.scalar(
            select(App).where(App.name == _app_name(enterprise_id))
        )
        app_created = False
        if app is None:
            app = App(
                enterprise_id=enterprise_id,
                name=_app_name(enterprise_id),
                kb_ids=[kb.id],
                api_key=_generate_api_key(),
                enabled=True,
                top_k=5,
                retrieval_mode="dense",
                prompt_template=None,  # 用系统默认模板
                model_params={},
            )
            session.add(app)
            session.commit()
            session.refresh(app)
            app_created = True

        return {
            "kb_id": kb.id,
            "doc_count": doc_count,
            "app_id": app.id,
            "app_created": app_created,
        }


def _main() -> int:
    parser = argparse.ArgumentParser(description="企业开箱播种（示例 KB + 预配置应用）")
    parser.add_argument("--enterprise-id", type=int, required=True, help="目标企业 id")
    parser.add_argument(
        "--seed-dir",
        type=Path,
        default=_DEFAULT_SEED_DIR,
        help=f"种子资源包目录（默认 {_DEFAULT_SEED_DIR}）",
    )
    args = parser.parse_args()

    if not args.seed_dir.is_dir():
        print(f"错误：种子目录不存在 {args.seed_dir}")
        return 1

    settings = get_settings()
    engine = make_engine(settings.mysql_url)
    session_factory = make_session_factory(engine)
    storage = LocalDiskStorage(root=settings.storage_root)
    embedder = create_embedder(settings)
    vector = create_vector(settings)
    vector.ensure_collection()

    try:
        result = seed_enterprise(
            session_factory,
            enterprise_id=args.enterprise_id,
            seed_dir=args.seed_dir,
            storage=storage,
            embedder=embedder,
            vector=vector,
            settings=settings,
        )
    except ValueError as e:
        print(f"错误：{e}")
        return 1

    print(f"播种完成：企业 id={args.enterprise_id}")
    print(f"  示例知识库 id={result['kb_id']}，文档 {result['doc_count']} 篇")
    if result["app_created"]:
        print(f"  已创建预配置应用 id={result['app_id']}（api_key 可在应用列表查看）")
    else:
        print(f"  复用已有预配置应用 id={result['app_id']}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
