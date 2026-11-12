
import pytest
from pydantic import ValidationError

from app.core.config import Settings, get_settings


def test_default_settings():
    config = Settings(_env_file=None)

    assert config.app_name == "E-Commerce Agent"
    assert config.app_env == "development"
    assert config.mysql_port == 3306
    assert config.redis_port == 6379


def test_secret_password_is_masked():
    config = Settings(
        _env_file=None,
        mysql_password="test_password",
    )

    assert "test_password" not in str(config.mysql_password)
    assert config.mysql_password.get_secret_value() == "test_password"


def test_settings_singleton():
    get_settings.cache_clear()

    first = get_settings()
    second = get_settings()

    assert first is second


# JWT configuration tests


def test_jwt_default_settings():
    config = Settings(_env_file=None)

    assert config.jwt_secret_key is not None
    assert config.jwt_secret_key.get_secret_value() == ""
    assert config.jwt_algorithm == "HS256"
    assert config.jwt_issuer == "ecommerce-agent"
    assert config.jwt_audience == "ecommerce-agent-api"
    assert config.jwt_access_token_expire_minutes == 15
    assert config.jwt_leeway_seconds == 30


def test_jwt_secret_key_accepts_valid_secret():
    config = Settings(
        _env_file=None,
        jwt_secret_key="a" * 32,
    )

    assert config.jwt_secret_key is not None
    assert len(config.jwt_secret_key.get_secret_value().encode("utf-8")) >= 32


def test_jwt_secret_key_rejects_short_secret():
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            jwt_secret_key="a" * 31,
        )


def test_production_requires_jwt_secret_key():
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            app_env="production",
        )


@pytest.mark.parametrize("field", ["jwt_issuer", "jwt_audience"])
@pytest.mark.parametrize("value", ["", "   "])
def test_jwt_identifiers_reject_empty_values(field, value):
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            **{field: value},
        )


@pytest.mark.parametrize("expire_minutes", [0, 1441])
def test_jwt_access_token_expire_minutes_rejects_out_of_range(
    expire_minutes,
):
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            jwt_access_token_expire_minutes=expire_minutes,
        )


def test_jwt_access_token_expire_minutes_accepts_boundary_values():
    for expire_minutes in (1, 1440):
        config = Settings(
            _env_file=None,
            jwt_access_token_expire_minutes=expire_minutes,
        )

        assert config.jwt_access_token_expire_minutes == expire_minutes


@pytest.mark.parametrize("leeway_seconds", [-1, 301])
def test_jwt_leeway_rejects_out_of_range(leeway_seconds):
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            jwt_leeway_seconds=leeway_seconds,
        )


def test_jwt_leeway_accepts_boundary_values():
    for leeway_seconds in (0, 300):
        config = Settings(
            _env_file=None,
            jwt_leeway_seconds=leeway_seconds,
        )

        assert config.jwt_leeway_seconds == leeway_seconds
