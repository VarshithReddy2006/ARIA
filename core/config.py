"""Centralised configuration system for ARIA using Pydantic Settings (core layer)."""

import os
from typing import Any, List, Optional
from dotenv import load_dotenv

# In development, local .env overrides system/IDE variables (preventing stale global keys from breaking local dev).
# In production, OS environment variables injected via Docker/Kubernetes/GitHub Actions must take precedence.
is_production = os.environ.get("APP_ENV", "development").lower() == "production"
load_dotenv(override=not is_production)

from pydantic import Field, field_validator  # noqa: E402
from pydantic_settings import BaseSettings, SettingsConfigDict  # noqa: E402


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        populate_by_name=True,
        extra="ignore",
        case_sensitive=False,
    )

    # App Settings
    app_env: str = Field("development", alias="APP_ENV")
    host: str = Field("0.0.0.0", alias="API_SERVER_HOST")
    port: int = Field(8001, alias="API_SERVER_PORT")
    log_level: str = Field("INFO", alias="LOG_LEVEL")
    log_format: str = Field("human", alias="LOG_FORMAT")  # "human" or "json"
    allowed_hosts: Any = Field(["*"], alias="ALLOWED_HOSTS")
    rate_limit_per_minute: int = Field(60, alias="RATE_LIMIT_PER_MINUTE")
    slow_request_threshold_seconds: float = Field(
        2.0, alias="SLOW_REQUEST_THRESHOLD_SECONDS"
    )
    api_key: Optional[str] = Field(None, alias="API_KEY")

    # Services Config
    github_token: Optional[str] = Field(None, alias="GITHUB_TOKEN")
    llm_provider: str = Field("gemini", alias="LLM_PROVIDER")
    deepseek_api_key: Optional[str] = Field(None, alias="DEEPSEEK_API_KEY")
    deepseek_base_url: str = Field(
        "https://integrate.api.nvidia.com/v1", alias="DEEPSEEK_BASE_URL"
    )
    deepseek_model: str = Field(
        "deepseek-ai/deepseek-v4-flash-0731", alias="DEEPSEEK_MODEL"
    )
    gemini_api_key: Optional[str] = Field(None, alias="GEMINI_API_KEY")
    gemini_model: str = Field("gemini-2.5-flash", alias="GEMINI_MODEL")
    embedding_model: str = Field("BAAI/bge-small-en-v1.5", alias="EMBEDDING_MODEL")

    # DB & Cache Config
    sqlite_db_path: str = Field("data/repo_understanding.db", alias="SQLITE_DB_PATH")
    chroma_db_path: str = Field("data/chroma_db", alias="CHROMA_DB_PATH")
    cache_file_path: str = Field("data/cache.json", alias="CACHE_FILE_PATH")
    cloned_repos_path: str = Field("data/cloned_repos", alias="CLONED_REPOS_PATH")

    # Vector Store & Qdrant Production Config (Phase 3)
    vector_store_backend: str = Field("qdrant", alias="VECTOR_STORE_BACKEND")
    vector_store_enable_fallback: bool = Field(
        True, alias="VECTOR_STORE_ENABLE_FALLBACK"
    )
    qdrant_url: Optional[str] = Field("http://127.0.0.1:6333", alias="QDRANT_URL")
    qdrant_api_key: Optional[str] = Field(None, alias="QDRANT_API_KEY")
    qdrant_grpc_port: Optional[int] = Field(6334, alias="QDRANT_GRPC_PORT")
    qdrant_prefer_grpc: bool = Field(True, alias="QDRANT_PREFER_GRPC")
    qdrant_timeout: float = Field(10.0, alias="QDRANT_TIMEOUT")
    qdrant_retry_attempts: int = Field(2, alias="QDRANT_RETRY_ATTEMPTS")

    # Frontend / CORS
    frontend_url: str = Field("http://localhost:4321", alias="FRONTEND_URL")

    # Queue & Build / Worker Concurrency
    worker_count: Optional[int] = Field(None, alias="WORKER_COUNT")
    aria_workers: Optional[int] = Field(None, alias="ARIA_WORKERS")
    web_concurrency: Optional[int] = Field(None, alias="WEB_CONCURRENCY")
    build_timeout: int = Field(1800, alias="BUILD_TIMEOUT")  # 30 minutes
    cache_size_limit: int = Field(1000, alias="CACHE_SIZE_LIMIT")

    @property
    def effective_workers(self) -> int:
        """Resolve effective worker count based on environment and configuration."""
        if self.worker_count and self.worker_count > 0:
            return self.worker_count
        if self.aria_workers and self.aria_workers > 0:
            return self.aria_workers
        if self.web_concurrency and self.web_concurrency > 0:
            return self.web_concurrency
        if self.app_env in ("development", "test"):
            return 1
        # In production default safely to min(4, max(2, cpu_count // 2))
        cpu_cnt = os.cpu_count() or 2
        return min(4, max(2, cpu_cnt // 2))

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    @field_validator(
        "api_key",
        "github_token",
        "deepseek_api_key",
        "deepseek_base_url",
        "deepseek_model",
        "gemini_api_key",
        "gemini_model",
        "llm_provider",
        "qdrant_api_key",
        mode="before",
    )
    @classmethod
    def strip_whitespace(cls, v: Optional[str]) -> Optional[str]:
        if isinstance(v, str):
            stripped = v.strip()
            return stripped if stripped else None
        return v

    @field_validator("deepseek_api_key")
    @classmethod
    def validate_api_key_if_deepseek(cls, v: Optional[str], info) -> Optional[str]:
        # Only validate when llm_provider is deepseek
        provider = info.data.get("llm_provider", "gemini")
        app_env = info.data.get("app_env", "development")
        if provider == "deepseek" and not v:
            if app_env == "production":
                raise ValueError(
                    "DEEPSEEK_API_KEY is required in production when LLM_PROVIDER is deepseek"
                )
        return v

    @field_validator("gemini_api_key")
    @classmethod
    def validate_api_key_if_gemini(cls, v: Optional[str], info) -> Optional[str]:
        # Only validate when llm_provider is gemini
        provider = info.data.get("llm_provider", "gemini")
        app_env = info.data.get("app_env", "development")
        if provider == "gemini" and not v:
            if app_env == "production":
                raise ValueError(
                    "GEMINI_API_KEY is required in production when LLM_PROVIDER is gemini"
                )
        return v

    @field_validator("allowed_hosts", mode="before")
    @classmethod
    def parse_allowed_hosts(cls, v: Any) -> List[str]:
        import json as _json

        if isinstance(v, str):
            v_str = v.strip()
            v_clean = v_str.replace('\\"', '"')
            if v_clean.startswith("[") and v_clean.endswith("]"):
                try:
                    res = _json.loads(v_clean)
                    if isinstance(res, list):
                        return [
                            str(item).strip().strip("'\"[] ")
                            for item in res
                            if str(item).strip().strip("'\"[] ")
                        ]
                except Exception:
                    pass
                v_clean = v_clean[1:-1].strip()

            # Split comma-separated string
            items = []
            for s in v_clean.split(","):
                cleaned = s.strip().strip("'\"[] ")
                if cleaned:
                    items.append(cleaned)
            return items if items else ["*"]

        if isinstance(v, list):
            return [
                str(item).strip().strip("'\"[] ")
                for item in v
                if str(item).strip().strip("'\"[] ")
            ]
        return ["*"]

    @field_validator("allowed_hosts")
    @classmethod
    def validate_allowed_hosts_in_production(cls, v: List[str], info) -> List[str]:
        app_env = info.data.get("app_env", "development")
        if app_env == "production":
            if not v or v == ["*"]:
                raise ValueError(
                    "ALLOWED_HOSTS must be explicitly configured in production "
                    '(e.g. ALLOWED_HOSTS=["api.yourdomain.com"]). '
                    "A wildcard (['*']) is not permitted."
                )
        return v


# Instantiate settings singleton
settings = Settings()


def get_settings(reload: bool = False) -> Settings:
    """Return an up-to-date Settings instance, reloading .env if requested."""
    global settings, is_production
    if reload:
        load_dotenv(override=not is_production)
        settings = Settings()
    return settings
