"""OSS 真实连通性验证（排期 §2 / Plan 1 Task 4 Step 4）：put/get/presign/delete 四步。

手动执行：填好 .env 的 OSS_* 四项后 `python scripts/verify_oss.py`。
四步全打印 OK = 对象存储风险清零；任何一步异常即停止并打印原因。
"""
import sys
from pathlib import Path

# 脚本位于仓库根 scripts/，app 包在 backend/ 下：锚定后任意工作目录可执行
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.config import get_settings  # noqa: E402
from app.core.storage import OssStorage  # noqa: E402


def main() -> int:
    settings = get_settings()
    missing = [
        field
        for field in ("oss_endpoint", "oss_access_key_id", "oss_access_key_secret", "oss_bucket")
        if not getattr(settings, field)
    ]
    if missing:
        print(f"缺少配置：{missing}（填 .env 的 OSS_* 四项后重试）")
        return 1

    storage = OssStorage(settings)
    key = "verify_oss/probe.txt"
    data = b"everkb verify_oss"

    storage.put_bytes(key, data)
    print(f"1/4 put    OK  {key} ({len(data)} bytes)")

    got = storage.get_bytes(key)
    assert got == data, "回读内容不一致"
    print("2/4 get    OK  内容一致")

    url = storage.presign(key, expires_sec=60)
    print(f"3/4 presign OK  {url[:80]}...")

    storage.delete(key)
    print("4/4 delete OK  （已清理探针对象）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
