
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
    """Validated claims extracted from an access token."""

    user_id: int
    jti: str
    issued_at: int
    expires_at: int


class TokenService:
    """Service responsible for creating and validating access tokens."""

    def __init__(self, config: Settings | None = None) -> None:
        self.config = config or get_settings()

        secret = self.config.jwt_secret_key

        if secret is None:
            raise RuntimeError(
                "JWT_SECRET_KEY must be configured before using TokenService"
            )

        self._secret_key = secret.get_secret_value()

        if len(self._secret_key.encode("utf-8")) < 32:
            raise RuntimeError(
                "JWT_SECRET_KEY must be at least 32 bytes long"
            )

    def create_access_token(self, user_id: int) -> str:
        """Create a signed JWT access token for a user."""

        if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0:
            raise ValueError("user_id must be a positive integer")

        issued_at = int(datetime.now(UTC).timestamp())

        expires_at = (
            issued_at
            + self.config.jwt_access_token_expire_minutes * 60
        )

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
        """Decode and validate an access token."""

        try:
            payload = jwt.decode(
                token,
                self._secret_key,
                algorithms=[self.config.jwt_algorithm],
                issuer=self.config.jwt_issuer,
                audience=self.config.jwt_audience,
                leeway=self.config.jwt_leeway_seconds,
                options={
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
        """Validate application-specific JWT claims."""

        subject = payload.get("sub")

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

        if payload.get("token_type") != "access":
            raise InvalidTokenException()

        return AccessTokenClaims(
            user_id=int(subject),
            jti=jti,
            issued_at=issued_at,
            expires_at=expires_at,
        )
