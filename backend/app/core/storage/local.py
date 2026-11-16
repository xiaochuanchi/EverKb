"""本地磁盘实现：key 即相对路径，文件落在 root 之下（默认实现，测试/本地开发用）。"""
from pathlib import Path


class LocalDiskStorage:
    """StorageClient 的本地磁盘实现（presign 为 local:// 占位，不产生真实 URL）。"""

    def __init__(self, root: str):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        return self.root / key

    def put_bytes(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def get_bytes(self, key: str) -> bytes:
        return self._path(key).read_bytes()  # 缺失时 Path 自抛 FileNotFoundError

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)  # 缺失静默

    def presign(self, key: str, expires_sec: int = 3600) -> str:
        return f"local://{key}"
