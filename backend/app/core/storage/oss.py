"""阿里云 OSS 实现：oss2 Bucket 薄封装（真实连通性走 scripts/verify_oss.py）。"""
import oss2

from app.core.config import Settings


class OssStorage:
    """StorageClient 的 OSS 实现；凭据/桶名来自 Settings（.env），不落库不进日志。"""

    def __init__(self, settings: Settings):
        auth = oss2.Auth(settings.oss_access_key_id, settings.oss_access_key_secret)
        self.bucket = oss2.Bucket(auth, settings.oss_endpoint, settings.oss_bucket)

    def put_bytes(self, key: str, data: bytes) -> None:
        self.bucket.put_object(key, data)

    def get_bytes(self, key: str) -> bytes:
        try:
            return self.bucket.get_object(key).read()  # 404 在读流时抛 NoSuchKey
        except oss2.exceptions.NoSuchKey:
            raise FileNotFoundError(key) from None

    def delete(self, key: str) -> None:
        # oss2 删除不存在的 key 返回 204，天然满足「缺失静默」
        self.bucket.delete_object(key)

    def presign(self, key: str, expires_sec: int = 3600) -> str:
        return self.bucket.sign_url("GET", key, expires_sec)
