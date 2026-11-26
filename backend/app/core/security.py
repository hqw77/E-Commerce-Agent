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
    """用 Argon2id 生成带随机盐的密码哈希.

    Args:
        plain_password: 明文密码.

    Returns:
        Argon2id 哈希字符串.
    """
    return _password_hasher.hash(plain_password)


def verify_password(
    plain_password: str,
    password_hash: str,
) -> bool:
    """校验明文密码与存储哈希是否匹配.

    Returns:
        True 表示匹配; 哈希损坏或不匹配返回 False.
    """
    try:
        return _password_hasher.verify(
            password_hash,
            plain_password,
        )
    except (VerificationError, InvalidHashError):
        return False


def verify_dummy_password(plain_password: str) -> bool:
    """对固定 dummy hash 执行一次真实校验, 用于拉平登录耗时.

    调用方必须忽略返回值; 该函数只用于防用户枚举.
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
    """判断存储哈希是否需要按当前 Argon2 参数重算.

    Returns:
        True 表示下次登录成功时应透明升级哈希.
    """
    try:
        return _password_hasher.check_needs_rehash(password_hash)
    except (VerificationError, InvalidHashError):
        return False
