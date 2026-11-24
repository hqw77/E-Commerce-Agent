
"""Access Token 的签发和校验.

Access Token 使用 JWT, 便于服务端无状态校验. Refresh Token 不在这里,
而是使用数据库中的不透明随机串, 因为它需要撤销, 轮换和重放检测.
"""

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import jwt

from app.core.config import Settings, get_settings
from app.core.exceptions import (
    InvalidTokenException,
    TokenExpiredException,
)


@dataclass(frozen=True, slots=True)
class AccessTokenClaims:
    """从 JWT 中解析并二次校验后的最小 claims 集合."""

    user_id: int
    jti: str
    issued_at: int
    expires_at: int


class TokenService:
    """Access Token 签发和校验服务."""

    def __init__(self, config: Settings | None = None) -> None:
        self.config = config or get_settings()

        secret = self.config.jwt_secret_key

        # 在服务初始化阶段检查密钥, 避免应用运行到签发 token 时才发现配置缺失.
        if secret is None:
            raise RuntimeError(
                "JWT_SECRET_KEY must be configured before using TokenService"
            )

        self._secret_key = secret.get_secret_value()

        # 过短的密钥容易被暴力破解, 这里做启动期保护.
        if len(self._secret_key.encode("utf-8")) < 32:
            raise RuntimeError(
                "JWT_SECRET_KEY must be at least 32 bytes long"
            )

    def create_access_token(self, user_id: int) -> str:
        """签发 Access Token. user_id 必须是正整数, 避免把布尔值当作用户 ID."""

        if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0:
            raise ValueError("user_id must be a positive integer")

        issued_at = int(datetime.now(UTC).timestamp())

        expires_at = (
            issued_at
            + self.config.jwt_access_token_expire_minutes * 60
        )

        # jti 为每次签发提供唯一标识, 便于后续审计或黑名单扩展.
        # issuer/audience 限定 token 只能被本服务接受.
        payload: dict[str, Any] = {
            "iss": self.config.jwt_issuer,
            "aud": self.config.jwt_audience,
            "sub": str(user_id),
            "iat": issued_at,
            "exp": expires_at,
            "jti": secrets.token_urlsafe(16),
            "token_type": "access",
        }

        return jwt.encode(
            payload,
            self._secret_key,
            algorithm=self.config.jwt_algorithm,
        )

    def decode_access_token(self, token: str) -> AccessTokenClaims:
        """校验签名, 时间, audience/issuer 和 claims, 返回可信的用户标识."""

        try:
            payload = jwt.decode(
                token,
                self._secret_key,
                algorithms=[self.config.jwt_algorithm],
                issuer=self.config.jwt_issuer,
                audience=self.config.jwt_audience,
                leeway=self.config.jwt_leeway_seconds,
                options={
                    # 明确要求所有安全相关 claims 存在, 不能依赖默认行为.
                    "require": [
                        "iss",
                        "aud",
                        "sub",
                        "iat",
                        "exp",
                        "jti",
                        "token_type",
                    ],
                    "strict_aud": True,
                },
            )

        except jwt.ExpiredSignatureError as exc:
            raise TokenExpiredException() from exc

        except jwt.InvalidTokenError as exc:
            raise InvalidTokenException() from exc

        return self._validate_application_claims(payload)

    @staticmethod
    def _validate_application_claims(
        payload: dict[str, Any],
    ) -> AccessTokenClaims:
        """校验业务层 claims, 防止算法或类型混淆导致身份被篡改."""

        subject = payload.get("sub")

        # 只接受规范的十进制字符串, 拒绝 "01", "1.0", 负数等歧义表示.
        if (
            not isinstance(subject, str)
            or not subject.isascii()
            or not subject.isdecimal()
            or str(int(subject)) != subject
            or int(subject) <= 0
        ):
            raise InvalidTokenException()

        issued_at = payload.get("iat")
        expires_at = payload.get("exp")
        jti = payload.get("jti")

        if (
            isinstance(issued_at, bool)
            or not isinstance(issued_at, int)
            or isinstance(expires_at, bool)
            or not isinstance(expires_at, int)
        ):
            raise InvalidTokenException()

        if expires_at <= issued_at:
            raise InvalidTokenException()

        if not isinstance(jti, str) or not jti:
            raise InvalidTokenException()

        # 防止 Refresh Token 或其他类型 token 被当作 Access Token 使用.
        if payload.get("token_type") != "access":
            raise InvalidTokenException()

        return AccessTokenClaims(
            user_id=int(subject),
            jti=jti,
            issued_at=issued_at,
            expires_at=expires_at,
        )
