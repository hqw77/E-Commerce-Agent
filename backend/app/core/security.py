"""密码哈希和校验工具.

使用 Argon2id 而不是普通 SHA 或 MD5, 以抵抗离线暴力破解和 GPU 加速攻击.
哈希函数是 CPU 密集型操作, 调用方应通过 asyncio.to_thread 放入线程池,
避免阻塞 FastAPI 的事件循环.
"""

import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

# 进程内共享一个 PasswordHasher, 复用其参数配置和内部状态.
# Create a shared password hasher.
_password_hasher = PasswordHasher()

# 用户不存在时也执行一次真实哈希校验, 使响应时间接近真实用户,
# 降低通过耗时差异枚举邮箱的风险.
# A fixed hash used to equalize login timing when the user does not exist.
# It is generated once per process, not on every request.
_DUMMY_PASSWORD_HASH = _password_hasher.hash(secrets.token_urlsafe(32))


def hash_password(plain_password: str) -> str:
    """
    Hash a plain-text password using Argon2id.

    A random salt is generated automatically.

    每次哈希使用随机盐, 相同密码也会得到不同结果, 因此不能直接比较哈希串.
    """
    return _password_hasher.hash(plain_password)


def verify_password(
    plain_password: str,
    password_hash: str,
) -> bool:
    """
    Verify a plain-text password against a stored password hash.

    Return False if the password does not match or the stored
    hash cannot be verified.

    哈希格式损坏时也返回 False, 避免把数据库内部格式泄露给调用方.
    """
    try:
        return _password_hasher.verify(
            password_hash,
            plain_password,
        )
    except (VerificationError, InvalidHashError):
        return False


def verify_dummy_password(plain_password: str) -> bool:
    """
    Run a password verification against a fixed dummy hash.

    The result is always False. Callers use this to spend the same
    Argon2id work whether or not the submitted email belongs to a
    registered user, which avoids leaking account existence through
    response timing.

    该函数只用于消耗与真实校验相当的计算时间, 调用方必须忽略其布尔返回值.
    """
    try:
        _password_hasher.verify(
            _DUMMY_PASSWORD_HASH,
            plain_password,
        )
    except (VerificationError, InvalidHashError):
        return False

    return True


def needs_rehash(password_hash: str) -> bool:
    """
    Check whether a password hash needs to be upgraded.

    Compare the stored hash parameters with the current
    PasswordHasher configuration.

    当 Argon2 参数升级后, 可在用户下次登录成功时透明地重算哈希.
    """
    try:
        return _password_hasher.check_needs_rehash(password_hash)
    except (VerificationError, InvalidHashError):
        return False
