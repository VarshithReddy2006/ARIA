import pytest
from pydantic import ValidationError
from backend.settings import Settings


def test_settings_default_load(monkeypatch):
    # Clear env variables that might be loaded from local .env
    monkeypatch.delenv("API_SERVER_PORT", raising=False)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)

    settings = Settings()

    # To be absolutely sure of default values, we construct Settings with no env file:
    class DefaultSettings(Settings):
        model_config = {}  # disable env file loading

    settings = DefaultSettings(_env_file=None)
    assert settings.llm_provider == "gemini"
    assert settings.port == 8001


def test_validation_fails_in_production_without_key():
    # When APP_ENV=production, llm_provider=gemini and GEMINI_API_KEY is empty, validation should fail
    with pytest.raises(ValidationError):
        Settings(APP_ENV="production", LLM_PROVIDER="gemini", GEMINI_API_KEY="")
    # When APP_ENV=production, llm_provider=deepseek and DEEPSEEK_API_KEY is empty, validation should fail
    with pytest.raises(ValidationError):
        Settings(APP_ENV="production", LLM_PROVIDER="deepseek", DEEPSEEK_API_KEY="")


def test_validation_passes_in_production_with_key():
    settings = Settings(
        APP_ENV="production",
        LLM_PROVIDER="gemini",
        GEMINI_API_KEY="test-key",
        ALLOWED_HOSTS=["api.example.com"],
    )
    assert settings.gemini_api_key == "test-key"

    settings_ds = Settings(
        APP_ENV="production",
        LLM_PROVIDER="deepseek",
        DEEPSEEK_API_KEY="test-key-ds",
        ALLOWED_HOSTS=["api.example.com"],
    )
    assert settings_ds.deepseek_api_key == "test-key-ds"


# ---------------------------------------------------------------------------
# H-3 Regression: ALLOWED_HOSTS wildcard rejected in production
# ---------------------------------------------------------------------------


def test_allowed_hosts_wildcard_rejected_in_production():
    """Production must not accept ALLOWED_HOSTS=['*']."""
    with pytest.raises(ValidationError):
        Settings(
            APP_ENV="production",
            LLM_PROVIDER="gemini",
            GEMINI_API_KEY="test-key",
            ALLOWED_HOSTS=["*"],
        )


def test_allowed_hosts_empty_rejected_in_production():
    """Production must not accept empty ALLOWED_HOSTS."""
    with pytest.raises(ValidationError):
        Settings(
            APP_ENV="production",
            LLM_PROVIDER="gemini",
            GEMINI_API_KEY="test-key",
            ALLOWED_HOSTS=[],
        )


def test_allowed_hosts_explicit_accepted_in_production():
    """Production accepts explicitly configured hostnames."""
    s = Settings(
        APP_ENV="production",
        LLM_PROVIDER="gemini",
        GEMINI_API_KEY="test-key",
        ALLOWED_HOSTS=["api.example.com", "app.example.com"],
    )
    assert s.allowed_hosts == ["api.example.com", "app.example.com"]


def test_allowed_hosts_wildcard_accepted_in_development():
    """Development/test environments may use wildcard ALLOWED_HOSTS."""
    s = Settings(
        APP_ENV="development",
        LLM_PROVIDER="gemini",
        ALLOWED_HOSTS=["*"],
    )
    assert s.allowed_hosts == ["*"]


# ---------------------------------------------------------------------------
# Self-Hosted Deployment Persistence Regression Tests
# ---------------------------------------------------------------------------


def test_sqlite_db_path_docker_persistent_path_preserved():
    """Configured docker persistent volume path /app/data/repo_understanding.db is preserved."""
    s = Settings(
        APP_ENV="production",
        LLM_PROVIDER="gemini",
        GEMINI_API_KEY="test-key",
        ALLOWED_HOSTS=["api.example.com"],
        SQLITE_DB_PATH="/app/data/repo_understanding.db",
    )
    assert s.sqlite_db_path == "/app/data/repo_understanding.db"


def test_sqlite_db_path_explicit_custom_absolute_path_preserved():
    """Any explicitly configured absolute path is preserved exactly without rewriting to /tmp."""
    custom_path = "/var/lib/aria/custom_repo.db"
    s = Settings(
        APP_ENV="production",
        LLM_PROVIDER="gemini",
        GEMINI_API_KEY="test-key",
        ALLOWED_HOSTS=["api.example.com"],
        SQLITE_DB_PATH=custom_path,
    )
    assert s.sqlite_db_path == custom_path


def test_sqlite_db_path_unset_production_fallback():
    """Unset SQLITE_DB_PATH in production falls back to /tmp/repo_understanding.db."""
    s = Settings(
        APP_ENV="production",
        LLM_PROVIDER="gemini",
        GEMINI_API_KEY="test-key",
        ALLOWED_HOSTS=["api.example.com"],
    )
    assert s.sqlite_db_path == "/tmp/repo_understanding.db"


def test_sqlite_db_path_default_relative_production_fallback():
    """Default relative path 'data/repo_understanding.db' in production falls back to /tmp/repo_understanding.db."""
    s = Settings(
        APP_ENV="production",
        LLM_PROVIDER="gemini",
        GEMINI_API_KEY="test-key",
        ALLOWED_HOSTS=["api.example.com"],
        SQLITE_DB_PATH="data/repo_understanding.db",
    )
    assert s.sqlite_db_path == "/tmp/repo_understanding.db"


def test_sqlite_db_path_unset_development_fallback():
    """Unset SQLITE_DB_PATH in development falls back to data/repo_understanding.db."""
    s = Settings(
        APP_ENV="development",
        LLM_PROVIDER="gemini",
    )
    assert s.sqlite_db_path == "data/repo_understanding.db"


def test_sqlite_db_path_explicit_relative_development():
    """Explicit relative path in development is preserved."""
    s = Settings(
        APP_ENV="development",
        LLM_PROVIDER="gemini",
        SQLITE_DB_PATH="custom/path/repo.db",
    )
    assert s.sqlite_db_path == "custom/path/repo.db"
