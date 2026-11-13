from functools import lru_cache
from typing import Literal

from pydantic import (
    Field,
    SecretStr,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application configuration.

    Configuration priority:
    Environment variables > .env file > default values.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "E-Commerce Agent"
    app_env: Literal["development", "testing", "production"] = "development"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"

    # Logging
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "DEBUG"
    log_format: Literal["console", "json"] = "console"

    # MySQL
    mysql_host: str = "127.0.0.1"
    mysql_port: int = 3306
    mysql_user: str = "root"
    mysql_password: SecretStr = SecretStr("")
    mysql_database: str = "ecommerce_agent"

    # Redis
    redis_host: str = "127.0.0.1"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: SecretStr | None = None

    # DeepSeek
    deepseek_api_key: SecretStr = SecretStr("")
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"

    # JWT
    jwt_secret_key: SecretStr = SecretStr("")
    jwt_algorithm: Literal["HS256"] = "HS256"
    jwt_issuer: str = Field(default="ecommerce-agent", min_length=1)
    jwt_audience: str = Field(default="ecommerce-agent-api", min_length=1)
    jwt_access_token_expire_minutes: int = Field(default=15, ge=1, le=1440)
    jwt_refresh_token_expire_days: int = Field(default=7, ge=1, le=365)
    jwt_leeway_seconds: int = Field(default=30, ge=0, le=300)

    # Orders / payments / after-sales
    order_payment_timeout_minutes: int = Field(default=30, ge=1, le=1440)
    after_sales_window_hours: int = Field(default=168, ge=1, le=720)

    # Alipay sandbox (empty means disabled)
    alipay_app_id: str = ""
    alipay_seller_id: str = ""
    alipay_private_key: SecretStr = SecretStr("")
    alipay_public_key: SecretStr = SecretStr("")
    alipay_gateway: str = "https://openapi.alipaydev.com/gateway.do"
    alipay_notify_url: str = ""
    alipay_return_url: str = ""
    alipay_frontend_return_url: str = ""

    @field_validator("jwt_issuer", "jwt_audience", mode="before")
    @classmethod
    def validate_jwt_identifiers(cls, value: str) -> str:
        """Reject empty or whitespace-only JWT identifiers."""
        if not isinstance(value, str) or not value.strip():
            raise ValueError("JWT issuer and audience must not be empty")

        return value.strip()

    @model_validator(mode="after")
    def validate_jwt_configuration(self) -> "Settings":
        secret = self.jwt_secret_key.get_secret_value()

        if self.app_env == "production" and not secret:
            raise ValueError("JWT_SECRET_KEY must be configured in production")

        if secret and len(secret.encode("utf-8")) < 32:
            raise ValueError("JWT_SECRET_KEY must be at least 32 bytes long")

        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Return a cached Settings instance.
    """
    return Settings()


settings = get_settings()
