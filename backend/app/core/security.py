"""鉴权安全原语（Task 14 / 计划文档 I8）：密码哈希 + JWT 签发与解码。

纯函数模块，不触库、不依赖 FastAPI——依赖缝判定：哈希与验签是纯库调用，
直接 import 不注入。

- 密码哈希：hashlib.pbkdf2_hmac（标准库零依赖，红线只禁框架不禁算法），
  格式串 `pbkdf2_sha256$轮数$盐hex$哈希hex` 存库（models.AdminUser.password_hash），
  带轮数与盐，算法/强度可平滑升级。
- JWT：pyjwt（requirements.txt 既有依赖），HS256 对称签名，payload 仅
  sub（admin_user.id）+ iat/exp；单 access token（2026-11-17 决策），无 refresh。
  注意：pyjwt ≥2.10 强制 sub 为字符串，故存 str(user.id)。
- 吊销语义（当前取舍）：无 Redis 黑名单前，JWT 无状态有效至过期（默认 24h）；
  改密/禁用账号后的旧 token 在过期前仍可用。require_admin 每请求查库
  is_active，账号禁用即时生效；登出黑名单/改密吊销随 I5 Redis 封装落地后补。
"""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import jwt

from app.core.config import Settings

PBKDF2_ROUNDS = 120_000  # 计划文档 I8：pbkdf2_hmac-sha256 120k 轮
JWT_ALGORITHM = "HS256"
_HASH_PREFIX = "pbkdf2_sha256"
_HASH_SEGMENTS = 4  # 前缀$轮数$盐$哈希


def hash_password(password: str) -> str:
    """生成 pbkdf2 格式串；盐每次随机（同密码两次哈希不同）。"""
    salt = secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ROUNDS)
    return f"{_HASH_PREFIX}${PBKDF2_ROUNDS}${salt.hex()}${derived.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """按格式串验签。格式不合法一律 False，不抛（脏数据当登录失败处理）。"""
    parts = stored.split("$")
    if len(parts) != _HASH_SEGMENTS or parts[0] != _HASH_PREFIX:
        return False
    try:
        rounds, salt_hex, hash_hex = int(parts[1]), parts[2], parts[3]
        salt, expected = bytes.fromhex(salt_hex), bytes.fromhex(hash_hex)
    except ValueError:
        return False
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, rounds)
    return hmac.compare_digest(derived, expected)  # 常量时间比较，防时序侧信道


def create_access_token(user_id: int, settings: Settings) -> str:
    """签发管理端 access JWT（sub=str(user.id)，exp=iat+jwt_expire_hours）。"""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(hours=settings.jwt_expire_hours),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str, settings: Settings) -> dict:
    """解码并验签。过期/签名不符/格式错误均抛 jwt.InvalidTokenError 子类，
    由调用方（api.auth.require_admin）折叠为 401。"""
    return jwt.decode(token, settings.jwt_secret, algorithms=[JWT_ALGORITHM])
