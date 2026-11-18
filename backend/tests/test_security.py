"""core/security.py 纯函数行为锁定（Task 14）：pbkdf2 格式串 + JWT。

不触库不触网（红线 3）；Settings 直接构造，不走 get_settings 缓存。
"""
import jwt
import pytest

from app.core.security import (
    PBKDF2_ROUNDS,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def _settings(**overrides):
    from app.core.config import Settings

    params = dict(jwt_secret="unit-secret", jwt_expire_hours=2)
    params.update(overrides)
    return Settings(**params)


# ── 密码哈希 ─────────────────────────────────────────────────────


def test_hash_password_format_is_versioned_string():
    stored = hash_password("test1234")
    parts = stored.split("$")
    assert len(parts) == 4
    assert parts[0] == "pbkdf2_sha256"
    assert int(parts[1]) == PBKDF2_ROUNDS  # 轮数随格式串存库，未来升级可平滑过渡
    assert len(bytes.fromhex(parts[2])) == 16  # 16 字节随机盐
    assert len(bytes.fromhex(parts[3])) == 32  # sha256 摘要


def test_verify_password_roundtrip():
    stored = hash_password("test1234")
    assert verify_password("test1234", stored)
    assert not verify_password("wrong-pass", stored)


def test_hash_password_salts_are_unique():
    assert hash_password("same-pass") != hash_password("same-pass")


@pytest.mark.parametrize("stored", ["", "md5$abc", "pbkdf2_sha256$x$y", "pbkdf2_sha256$abc$zz$00$11"])
def test_verify_password_malformed_stored_hash_is_false_not_raise(stored):
    """脏数据/旧格式哈希一律当验证失败，绝不抛 500。"""
    assert verify_password("whatever", stored) is False


# ── JWT ──────────────────────────────────────────────────────────


def test_token_roundtrip_carries_user_id():
    token = create_access_token(42, _settings())
    payload = decode_access_token(token, _settings())
    assert payload["sub"] == "42"  # pyjwt ≥2.10 强制 sub 为字符串
    assert payload["exp"] > payload["iat"]


def test_decode_with_wrong_secret_rejected():
    token = create_access_token(1, _settings())
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(token, _settings(jwt_secret="other-secret"))


def test_decode_expired_token_rejected():
    settings = _settings(jwt_expire_hours=-1)  # exp 落在过去
    token = create_access_token(1, settings)
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(token, settings)
