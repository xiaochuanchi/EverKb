"""存储抽象（Task 4）：Protocol 四方法 + LocalDiskStorage 行为 + create_storage 分派。

红线 3：本文件不发任何网络调用——OssStorage 只做离线构造（Auth/Bucket 构造
不出网），真实连通性走 scripts/verify_oss.py（有凭据时手动执行）。
"""
import pytest

from app.core.config import Settings
from app.core.storage import LocalDiskStorage, OssStorage, create_storage


def test_put_get_roundtrip(tmp_path):
    s = LocalDiskStorage(root=str(tmp_path / "storage"))
    s.put_bytes("kb/1/doc/2/source.md", b"# hello")
    assert s.get_bytes("kb/1/doc/2/source.md") == b"# hello"


def test_get_missing_raises_file_not_found(tmp_path):
    s = LocalDiskStorage(root=str(tmp_path / "storage"))
    with pytest.raises(FileNotFoundError):
        s.get_bytes("kb/9/doc/9/none.md")


def test_delete_then_get_raises_and_delete_missing_silent(tmp_path):
    """删除后 get 抛 FileNotFoundError；delete 不存在的 key 静默（协议契约）。"""
    s = LocalDiskStorage(root=str(tmp_path / "storage"))
    s.put_bytes("a/b.txt", b"x")
    s.delete("a/b.txt")
    with pytest.raises(FileNotFoundError):
        s.get_bytes("a/b.txt")
    s.delete("a/never-existed.txt")


def test_presign_local_scheme(tmp_path):
    """local 实现的 presign 返回 local://{key}（测试/本地占位）。"""
    s = LocalDiskStorage(root=str(tmp_path / "storage"))
    assert s.presign("kb/1/doc/2/content.md") == "local://kb/1/doc/2/content.md"


def test_create_storage_dispatch_local(settings):
    assert isinstance(create_storage(settings), LocalDiskStorage)


def test_create_storage_dispatch_oss(tmp_path):
    """OSS 分派返回 OssStorage（离线构造，凭据为测试占位值）。"""
    s = Settings(
        mysql_url="sqlite:///:memory:",
        storage_backend="oss",
        storage_root=str(tmp_path / "storage"),
        worker_enabled=False,
        oss_endpoint="https://oss-cn-hangzhou.aliyuncs.com",
        oss_access_key_id="test-key",
        oss_access_key_secret="test-secret",
        oss_bucket="test-bucket",
    )
    assert isinstance(create_storage(s), OssStorage)
