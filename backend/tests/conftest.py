"""pytest 共享夹具：测试 Settings（SQLite 内存库）+ LocalDiskStorage 注入 + 管线环境。

红线 3：测试不发真实网络调用——vector/embedder 注入 Fake 双件套。
"""
import hashlib
import io
import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.db import init_db, make_engine, make_session_factory
from app.core.storage import LocalDiskStorage
from app.main import create_app
from app.models import Document, DocumentStatus, KnowledgeBase, SourceType
from app.services.embedding import FakeEmbedder
from app.services.vector import FakeVector


def make_test_settings(tmp_path, **overrides) -> Settings:
    params = dict(
        mysql_url="sqlite:///:memory:",
        storage_backend="local",
        storage_root=str(tmp_path / "storage"),
        worker_enabled=False,
        jwt_secret="test",
        admin_username="admin",
        admin_password_hash=hashlib.sha256(b"test1234").hexdigest(),
    )
    params.update(overrides)
    return Settings(**params)


@pytest.fixture()
def settings(tmp_path) -> Settings:
    return make_test_settings(tmp_path)


@pytest.fixture()
def client(tmp_path, settings) -> TestClient:
    storage = LocalDiskStorage(root=str(tmp_path / "storage"))
    app = create_app(settings, storage=storage)
    with TestClient(app) as c:
        yield c


# ── 管线测试环境（Task 10）：Fake 双件套 + 造文档 helper ────────────────


def source_key(kb_id: int, doc_id: int, ext: str) -> str:
    """对象路径约定（Global Constraints）：kb/{kb_id}/doc/{doc_id}/source.{ext}。"""
    return f"kb/{kb_id}/doc/{doc_id}/source.{ext}"


def make_docx_bytes(sections: list[tuple[str, list[str]]]) -> bytes:
    """按（标题, 正文段列表）构造 docx：每 section 一个 Heading 1，保证按标题切段。"""
    from docx import Document as build_docx

    doc = build_docx()
    for title, paras in sections:
        doc.add_heading(title, level=1)
        for p in paras:
            doc.add_paragraph(p)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


@pytest.fixture()
def pipeline_env(tmp_path):
    """管线测试环境：SQLite 会话工厂 + 本地存储 + Fake 双件套（测试不触网）。"""
    engine = make_engine("sqlite:///:memory:")
    init_db(engine)
    factory = make_session_factory(engine)
    env = SimpleNamespace(
        factory=factory,
        storage=LocalDiskStorage(root=str(tmp_path / "storage")),
        vector=FakeVector(dim=8),
        embedder=FakeEmbedder(dim=8),
        settings=make_test_settings(tmp_path),
    )
    env.session = factory()
    yield env
    env.session.close()


@pytest.fixture()
def make_document(pipeline_env):
    """造 Document 行：kb 兜底创建，oss_key 按路径约定回填后提交。"""

    def _make(
        *,
        kb=None,
        source_type=SourceType.UPLOAD,
        file_type="docx",
        name="测试文档",
        enabled=True,
        status=DocumentStatus.UPLOADED,
        version=1,
        source_url=None,
    ) -> Document:
        session = pipeline_env.session
        if kb is None:
            kb = KnowledgeBase(name=f"kb-{uuid.uuid4().hex[:8]}")
            session.add(kb)
            session.flush()
        ext = "html" if source_type == SourceType.WEBPAGE else file_type
        if source_type == SourceType.WEBPAGE and source_url is None:
            source_url = "https://example.com/article"
        doc = Document(
            kb_id=kb.id,
            name=name,
            source_type=source_type,
            file_type=file_type,
            oss_key="",
            source_url=source_url,
            status=status,
            version=version,
            enabled=enabled,
        )
        session.add(doc)
        session.flush()
        doc.oss_key = source_key(doc.kb_id, doc.id, ext)
        session.commit()
        return doc

    return _make


@pytest.fixture()
def seed_source(pipeline_env):
    """预置 source 对象字节到存储层。"""

    def _seed(doc: Document, data: bytes) -> None:
        pipeline_env.storage.put_bytes(doc.oss_key, data)

    return _seed


@pytest.fixture()
def process_doc(pipeline_env):
    """按依赖注入约定调 process_document，省去逐参传 Fake。"""

    def _run(doc_id: int, *, session=None):
        from app.services.pipeline import process_document

        return process_document(
            session or pipeline_env.session,
            doc_id,
            storage=pipeline_env.storage,
            embedder=pipeline_env.embedder,
            vector=pipeline_env.vector,
            settings=pipeline_env.settings,
        )

    return _run


@pytest.fixture()
def run_pending(pipeline_env):
    """按依赖注入约定调 run_pending。"""

    def _run(*, session=None):
        from app.services.pipeline import run_pending as _run_pending

        return _run_pending(
            pipeline_env.factory,
            storage=pipeline_env.storage,
            embedder=pipeline_env.embedder,
            vector=pipeline_env.vector,
            settings=pipeline_env.settings,
        )

    return _run
