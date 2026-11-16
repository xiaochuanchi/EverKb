"""pytest 共享夹具：测试 Settings（SQLite 内存库）+ LocalDiskStorage 注入。

红线 3：测试不发真实网络调用；vector/embedder 先占位 None，后续任务补 Fake。
"""
import hashlib

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.storage import LocalDiskStorage
from app.main import create_app


def make_test_settings(tmp_path) -> Settings:
    return Settings(
        mysql_url="sqlite:///:memory:",
        storage_backend="local",
        storage_root=str(tmp_path / "storage"),
        worker_enabled=False,
        jwt_secret="test",
        admin_username="admin",
        admin_password_hash=hashlib.sha256(b"test1234").hexdigest(),
    )


@pytest.fixture()
def settings(tmp_path) -> Settings:
    return make_test_settings(tmp_path)


@pytest.fixture()
def client(tmp_path, settings) -> TestClient:
    storage = LocalDiskStorage(root=str(tmp_path / "storage"))
    app = create_app(settings, storage=storage)
    with TestClient(app) as c:
        yield c
