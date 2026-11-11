
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
