"""应用配置中心.

所有运行参数在这里集中声明, 业务代码只依赖 Settings 对象, 不直接读取环境变量.
配置优先级为: 环境变量 > .env 文件 > 字段默认值.
"""

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

    使用 pydantic-settings 统一完成类型转换和启动期校验, 避免配置错误拖到请求阶段才暴露.
    SecretStr 用于密码/API Key 等敏感值, 防止日志或 repr 直接输出明文.
    """

    # 指定 .env 路径和大小写规则. extra="ignore" 允许环境里存在未声明的变量,
    # 避免部署环境中的无关变量导致应用启动失败.
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # 应用级配置: 环境标识影响安全校验, debug 同时控制 SQL echo 等开发行为.
    # Application
    app_name: str = "E-Commerce Agent"
    app_env: Literal["development", "testing", "production"] = "development"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"

    # Logging
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "DEBUG"
    log_format: Literal["console", "json"] = "console"

    # 数据库连接参数. 密码使用 SecretStr, 只有显式 get_secret_value() 才能取出.
    # MySQL
    mysql_host: str = "127.0.0.1"
    mysql_port: int = 3306
    mysql_user: str = "root"
    mysql_password: SecretStr = SecretStr("")
    mysql_database: str = "ecommerce_agent"

    # Redis 用于限流, 会话, 锁和临时确认状态, 不是业务数据的最终权威来源.
    # Redis
    redis_host: str = "127.0.0.1"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: SecretStr | None = None

    # DeepSeek
    deepseek_api_key: SecretStr = SecretStr("")
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"

    # Agent LLM (TASK-006.1)
    agent_llm_timeout_seconds: int = Field(default=30, ge=1, le=300)
    agent_llm_max_retries: int = Field(default=1, ge=0, le=5)
    agent_temperature: float = Field(default=0.2, ge=0, le=2)
    agent_max_output_tokens: int = Field(default=1024, ge=1, le=8192)

    # Agent runtime (TASK-006.2-006.6)
    agent_enabled: bool = True
    agent_max_input_chars: int = Field(default=4000, ge=1, le=100000)
    agent_max_output_chars: int = Field(default=8000, ge=1, le=100000)
    agent_max_history_messages: int = Field(default=20, ge=1, le=200)
    agent_max_history_chars: int = Field(default=8000, ge=1, le=100000)
    agent_max_rag_context_chars: int = Field(default=6000, ge=0, le=100000)
    agent_max_context_chars: int = Field(default=14000, ge=1, le=200000)
    agent_conversation_ttl_seconds: int = Field(
        default=604800,
        ge=60,
        le=2592000,
    )
    agent_conversation_lock_ttl_ms: int = Field(default=60000, ge=1000)
    agent_max_execution_seconds: int = Field(default=40, ge=1, le=300)
    agent_conversation_lock_safety_margin_seconds: int = Field(
        default=15,
        ge=0,
        le=300,
    )
    agent_rag_top_k: int = Field(default=5, ge=1, le=20)
    # TASK-021.2: no-answer policy uses a score band plus lexical evidence.
    # Values are offline-calibrated candidates, not production certification.
    agent_rag_min_score: float = Field(default=0.60, ge=0.0, le=1.0)
    agent_rag_high_confidence_score: float = Field(
        default=0.625,
        ge=0.0,
        le=1.0,
    )
    agent_rag_min_evidence_coverage: float = Field(
        default=0.50,
        ge=0.0,
        le=1.0,
    )
    agent_rate_limit_per_minute: int = Field(default=30, ge=1, le=10000)
    agent_max_tool_calls_per_turn: int = Field(default=4, ge=1, le=20)
    agent_action_confirmation_ttl_seconds: int = Field(
        default=300,
        ge=30,
        le=3600,
    )
    agent_approval_ttl_seconds: int = Field(
        default=86400,
        ge=300,
        le=604800,
    )

    # JWT 配置. issuer/audience 用于限制 token 的签发和消费范围,
    # leeway 容忍客户端与服务端之间的少量时钟偏差.
    # JWT
    jwt_secret_key: SecretStr = SecretStr("")
    jwt_algorithm: Literal["HS256"] = "HS256"
    jwt_issuer: str = Field(default="ecommerce-agent", min_length=1)
    jwt_audience: str = Field(default="ecommerce-agent-api", min_length=1)
    jwt_access_token_expire_minutes: int = Field(default=15, ge=1, le=1440)
    jwt_refresh_token_expire_days: int = Field(default=7, ge=1, le=365)
    jwt_leeway_seconds: int = Field(default=30, ge=0, le=300)

    # 交易业务时间窗口. 订单过期时间仅作为历史字段保留, 售后窗口继续使用.
    # Orders / after-sales
    order_payment_timeout_minutes: int = Field(default=30, ge=1, le=1440)
    after_sales_window_hours: int = Field(default=168, ge=1, le=720)

    # RAG 配置. Qdrant 只保存向量索引, 文档/版本/Chunk 的权威数据仍在 MySQL.
    # RAG / knowledge base
    rag_enabled: bool = True
    rag_qdrant_url: str = "http://127.0.0.1:6333"
    rag_qdrant_api_key: SecretStr = SecretStr("")
    rag_collection: str = "knowledge_chunks_bge_m3_v1"
    rag_embedding_model: str = "BAAI/bge-m3"
    rag_embedding_dimension: int = Field(default=1024, ge=1)
    rag_embedding_device: str = "cpu"
    rag_embedding_batch_size: int = Field(default=8, ge=1, le=128)
    rag_embedding_cache_dir: str = ".cache/huggingface"
    rag_top_k: int = Field(default=5, ge=1, le=50)
    rag_max_candidates: int = Field(default=20, ge=1, le=200)
    rag_chunk_target_tokens: int = Field(default=500, ge=50)
    rag_chunk_max_tokens: int = Field(default=700, ge=50)
    rag_chunk_overlap_tokens: int = Field(default=80, ge=0)
    rag_max_file_size_mb: int = Field(default=20, ge=1, le=200)
    rag_storage_dir: str = "storage/knowledge"

    @field_validator("jwt_issuer", "jwt_audience", mode="before")
    @classmethod
    def validate_jwt_identifiers(cls, value: str) -> str:
        """
        拒绝空字符串或仅空白的 JWT 标识.

        issuer 和 audience 是 token 校验的一部分, 空值会让 token 被任意服务接受,
        因此在配置加载阶段直接失败.
        """
        if not isinstance(value, str) or not value.strip():
            raise ValueError("JWT issuer and audience must not be empty")

        return value.strip()

    @model_validator(mode="after")
    def validate_jwt_configuration(self) -> "Settings":
        """生产环境要求强 JWT 密钥, 并在启动期校验长度."""
        # 生产环境必须配置足够长的 JWT 密钥, 这是启动前的 fail-fast 校验.
        secret = self.jwt_secret_key.get_secret_value()

        if self.app_env == "production" and not secret:
            raise ValueError("JWT_SECRET_KEY must be configured in production")

        if secret and len(secret.encode("utf-8")) < 32:
            raise ValueError("JWT_SECRET_KEY must be at least 32 bytes long")

        return self

    @model_validator(mode="after")
    def validate_agent_lock_configuration(self) -> "Settings":
        """保证会话锁 TTL 大于执行超时加安全余量."""
        # 会话锁必须在请求执行超时和安全余量之后才过期,
        # 否则锁提前释放可能让同一会话被并发处理.
        lock_seconds = self.agent_conversation_lock_ttl_ms / 1000
        required = (
            self.agent_max_execution_seconds
            + self.agent_conversation_lock_safety_margin_seconds
        )
        if required >= lock_seconds:
            raise ValueError(
                "AGENT_MAX_EXECUTION_SECONDS plus safety margin must be "
                "less than AGENT_CONVERSATION_LOCK_TTL_MS"
            )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """返回进程级缓存的 Settings.

    配置只解析和校验一次; 测试需要覆盖时显式构造 Settings,
    不要修改这个全局单例.
    """
    return Settings()


# 进程级配置单例; 启动时完成校验.
settings = get_settings()
