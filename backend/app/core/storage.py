"""可插拔对象存储抽象（设计文档 §4 存储设计）。

对象路径约定：kb/{kb_id}/doc/{doc_id}/source.{ext} 与 kb/{kb_id}/doc/{doc_id}/content.md
Task 4 将在 oss.py 落 OssStorage 实现（同一 Protocol）；Task 6 起管线只依赖 Protocol。
"""
from pathlib import Path
from typing import Protocol


class StorageClient(Protocol):
    """存储客户端统一接口：本地磁盘与阿里云 OSS 各给一个实现。"""

    def save(self, key: str, data: bytes) -> None: ...

    def read(self, key: str) -> bytes: ...

    def delete(self, key: str) -> None: ...

    def exists(self, key: str) -> bool: ...


class LocalDiskStorage:
    """本地磁盘实现：key 即相对路径，文件落在 root 之下（默认实现）。"""

    def __init__(self, root: str):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        return self.root / key

    def save(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def read(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def exists(self, key: str) -> bool:
        return self._path(key).exists()
