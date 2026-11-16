"""StorageClient Protocol：local/oss 两实现的统一接口（设计文档 §4 存储设计）。"""
from typing import Protocol


class StorageClient(Protocol):
    """存储客户端统一接口；对象路径约定 kb/{kb_id}/doc/{doc_id}/…（Task 10 起管线只依赖本协议）。"""

    def put_bytes(self, key: str, data: bytes) -> None: ...

    def get_bytes(self, key: str) -> bytes:
        """缺失抛 FileNotFoundError。"""
        ...

    def delete(self, key: str) -> None:
        """缺失静默（幂等删除）。"""
        ...

    def presign(self, key: str, expires_sec: int = 3600) -> str:
        """预签名下载 URL；local 实现返回 local://{key}（测试/本地占位）。"""
        ...
