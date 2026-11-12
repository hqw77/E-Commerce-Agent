
import time

import jwt
import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.core.exceptions import (
    InvalidTokenException,
    TokenExpiredException,
)
from app.core.token import AccessTokenClaims, TokenService

TEST_SECRET = "test-secret-key-for-jwt-at-least-32-bytes"


@pytest.fixture
def token_service() -> TokenService:
    """Create a TokenService with an isolated test configuration."""
    config = Settings(
        app_env="testing",
        jwt_secret_key=SecretStr(TEST_SECRET),
    )
    return TokenService(config)


def _encode_test_token(
    payload: dict,
    secret: str = TEST_SECRET,
) -> str:
    """Encode a JWT for validation tests."""
    return jwt.encode(
        payload,
        secret,
        algorithm="HS256",
    )


def _valid_payload() -> dict:
    """Return a valid access token payload."""
    now = int(time.time())

    return {
        "iss": "ecommerce-agent",
        "aud": "ecommerce-agent-api",
        "sub": "1001",
        "iat": now,
        "exp": now + 900,
        "jti": "test-token-id",
        "token_type": "access",
    }


def test_create_access_token(token_service: TokenService) -> None:
    token = token_service.create_access_token(user_id=1001)

    assert isinstance(token, str)
    assert len(token.split(".")) == 3


def test_create_access_token_contains_valid_claims(
    token_service: TokenService,
) -> None:
    token = token_service.create_access_token(user_id=1001)

    claims = token_service.decode_access_token(token)

    assert isinstance(claims, AccessTokenClaims)
    assert claims.user_id == 1001
    assert isinstance(claims.jti, str)
    assert claims.jti
    assert claims.expires_at - claims.issued_at == 900


def test_create_access_token_generates_unique_jti(
    token_service: TokenService,
) -> None:
    token1 = token_service.create_access_token(user_id=1001)
    token2 = token_service.create_access_token(user_id=1001)

    claims1 = token_service.decode_access_token(token1)
    claims2 = token_service.decode_access_token(token2)

    assert claims1.jti != claims2.jti


@pytest.mark.parametrize(
    "user_id",
    [0, -1, True, False, 1.5, "1001"],
)
def test_create_access_token_rejects_invalid_user_id(
    token_service: TokenService,
    user_id: object,
) -> None:
    with pytest.raises(ValueError):
        token_service.create_access_token(user_id)  # type: ignore[arg-type]


def test_decode_expired_token(
    token_service: TokenService,
) -> None:
    now = int(time.time())

    payload = _valid_payload()
    payload["iat"] = now - 3600
    payload["exp"] = now - 1800

    token = _encode_test_token(payload)

    with pytest.raises(TokenExpiredException):
        token_service.decode_access_token(token)


def test_decode_token_with_invalid_signature(
    token_service: TokenService,
) -> None:
    token = _encode_test_token(
        _valid_payload(),
        secret="another-secret-key-for-jwt-at-least-32-bytes",
    )

    with pytest.raises(InvalidTokenException):
        token_service.decode_access_token(token)


def test_decode_token_with_invalid_audience(
    token_service: TokenService,
) -> None:
    payload = _valid_payload()
    payload["aud"] = "another-api"

    token = _encode_test_token(payload)

    with pytest.raises(InvalidTokenException):
        token_service.decode_access_token(token)


def test_decode_token_with_invalid_issuer(
    token_service: TokenService,
) -> None:
    payload = _valid_payload()
    payload["iss"] = "another-issuer"

    token = _encode_test_token(payload)

    with pytest.raises(InvalidTokenException):
        token_service.decode_access_token(token)


def test_decode_token_with_invalid_token_type(
    token_service: TokenService,
) -> None:
    payload = _valid_payload()
    payload["token_type"] = "refresh"

    token = _encode_test_token(payload)

    with pytest.raises(InvalidTokenException):
        token_service.decode_access_token(token)


def test_decode_token_with_invalid_subject(
    token_service: TokenService,
) -> None:
    payload = _valid_payload()
    payload["sub"] = "001"

    token = _encode_test_token(payload)

    with pytest.raises(InvalidTokenException):
        token_service.decode_access_token(token)


def test_decode_token_with_missing_required_claim(
    token_service: TokenService,
) -> None:
    payload = _valid_payload()
    payload.pop("jti")

    token = _encode_test_token(payload)

    with pytest.raises(InvalidTokenException):
        token_service.decode_access_token(token)


def test_decode_malformed_token(
    token_service: TokenService,
) -> None:
    with pytest.raises(InvalidTokenException):
        token_service.decode_access_token("this-is-not-a-valid-jwt")


def test_token_service_rejects_missing_secret() -> None:
    config = Settings(
        app_env="testing",
        jwt_secret_key="",
    )

    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
        TokenService(config)
