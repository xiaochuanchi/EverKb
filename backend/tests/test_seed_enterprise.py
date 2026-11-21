"""M4 播种幂等锁定测试：scripts/seed_enterprise.py 的 seed_enterprise 函数。

用 SQLite 内存库 + Fake 双件套（pipeline_env）验证播种行为，不发真实网络。
锁定点（方案 §11「播种幂等可重跑」）：
- 首次播种：建示例 KB + 入库文档（处理到完成）+ 建预配置应用；
- 重复播种：复用同一 KB 与应用（不重复建），已完成文档跳过；
- 播种前企业必须存在（不存在抛 ValueError）。
"""
from pathlib import Path

import pytest

from app.models import App, Document, DocumentStatus, Enterprise, EnterpriseStatus, KnowledgeBase


def _seed_dir(tmp_path, files: dict[str, str]) -> Path:
    d = tmp_path / "seed"
    d.mkdir()
    for name, content in files.items():
        (d / name).write_text(content, encoding="utf-8")
    return d


def _make_enterprise(pipeline_env, ent_id=None) -> Enterprise:
    session = pipeline_env.session
    ent = Enterprise(name=f"测试企业-{ent_id or 'x'}", status=EnterpriseStatus.TRIAL)
    session.add(ent)
    session.commit()
    session.refresh(ent)
    return ent


def _seed(seed_dir, ent, pipeline_env):
    from scripts.seed_enterprise import seed_enterprise

    return seed_enterprise(
        pipeline_env.factory,
        enterprise_id=ent.id,
        seed_dir=seed_dir,
        storage=pipeline_env.storage,
        embedder=pipeline_env.embedder,
        vector=pipeline_env.vector,
        settings=pipeline_env.settings,
    )


def test_seed_creates_kb_docs_and_app(pipeline_env, tmp_path):
    """首次播种：建示例 KB + 入库文档（处理完成）+ 建预配置应用。"""
    ent = _make_enterprise(pipeline_env)
    seed_dir = _seed_dir(tmp_path, {"手册.md": "# 手册\n\n这是第一段。\n\n这是第二段。\n"})

    result = _seed(seed_dir, ent, pipeline_env)

    session = pipeline_env.session
    kb = session.get(KnowledgeBase, result["kb_id"])
    assert kb is not None
    assert kb.enterprise_id == ent.id
    assert kb.name == f"示例知识库-{ent.id}"

    # 文档处理完成
    doc = session.query(Document).filter(Document.kb_id == kb.id).first()
    assert doc is not None
    assert doc.status == DocumentStatus.COMPLETED
    assert doc.enterprise_id == ent.id

    # 预配置应用
    app = session.get(App, result["app_id"])
    assert app is not None
    assert app.enterprise_id == ent.id
    assert app.kb_ids == [kb.id]
    assert app.api_key.startswith("sk-")
    assert result["app_created"] is True


def test_seed_idempotent_on_rerun(pipeline_env, tmp_path):
    """重复播种：复用同一 KB 与应用，不重复建，已完成文档跳过。"""
    ent = _make_enterprise(pipeline_env)
    seed_dir = _seed_dir(tmp_path, {"手册.md": "# 手册\n\n内容一。\n\n内容二。\n"})

    first = _seed(seed_dir, ent, pipeline_env)
    second = _seed(seed_dir, ent, pipeline_env)

    session = pipeline_env.session
    # KB 与应用都是复用的（id 一致）
    assert second["kb_id"] == first["kb_id"]
    assert second["app_id"] == first["app_id"]
    assert second["app_created"] is False

    # 没有重复的 KB / 应用行
    kb_count = session.query(KnowledgeBase).filter(
        KnowledgeBase.enterprise_id == ent.id
    ).count()
    assert kb_count == 1
    app_count = session.query(App).filter(App.enterprise_id == ent.id).count()
    assert app_count == 1

    # 文档只有一篇（未重复）
    doc_count = session.query(Document).filter(
        Document.kb_id == first["kb_id"]
    ).count()
    assert doc_count == 1


def test_seed_requires_existing_enterprise(pipeline_env, tmp_path):
    """播种前企业必须存在：不存在的 id 抛 ValueError。"""
    seed_dir = _seed_dir(tmp_path, {"a.md": "# a\n\n正文。\n"})
    with pytest.raises(ValueError):
        from scripts.seed_enterprise import seed_enterprise

        seed_enterprise(
            pipeline_env.factory,
            enterprise_id=999999,
            seed_dir=seed_dir,
            storage=pipeline_env.storage,
            embedder=pipeline_env.embedder,
            vector=pipeline_env.vector,
            settings=pipeline_env.settings,
        )


def test_seed_empty_dir_creates_kb_and_app_without_docs(pipeline_env, tmp_path):
    """空种子目录：仍建 KB 与应用，但不入库任何文档。"""
    ent = _make_enterprise(pipeline_env)
    seed_dir = _seed_dir(tmp_path, {})

    result = _seed(seed_dir, ent, pipeline_env)

    assert result["doc_count"] == 0
    assert result["app_created"] is True
