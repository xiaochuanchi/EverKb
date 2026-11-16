"""可插拔对象存储（Task 4）：base Protocol + local/oss 实现 + 工厂。

对象路径约定：kb/{kb_id}/doc/{doc_id}/source.{ext} 与 kb/{kb_id}/doc/{doc_id}/content.md。
re-export 保持 app.core.storage 的导入路径不变（main/conftest 无感迁移）。
"""
from app.core.config import Settings
from app.core.storage.base import StorageClient
from app.core.storage.local import LocalDiskStorage
from app.core.storage.oss import OssStorage


def create_storage(settings: Settings) -> StorageClient:
    """按 storage_backend 分派（local | oss）。"""
    if settings.storage_backend == "oss":
        return OssStorage(settings)
    return LocalDiskStorage(root=settings.storage_root)


__all__ = ["LocalDiskStorage", "OssStorage", "StorageClient", "create_storage"]
