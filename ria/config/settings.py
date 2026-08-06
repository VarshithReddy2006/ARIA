"""Application Settings and Configuration for RIA."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, field_validator

from ria.domain.errors import ConfigurationError


class _EnvironmentValidationBoundary(BaseModel):
    """Keep environment-input validation at the configuration boundary."""

    environment: str

    @field_validator("environment")
    @classmethod
    def normalize_environment(cls, value: str) -> str:
        return value.lower()


@dataclass(frozen=True, slots=True)
class ObservabilitySettings:
    """Immutable observability settings container."""

    log_level: str = "INFO"
    log_format: str = "human"
    metrics_enabled: bool = False

    def __post_init__(self) -> None:
        """Normalize levels supplied by environment-driven configuration."""
        object.__setattr__(self, "log_level", self.log_level.upper())


@dataclass(frozen=True, slots=True)
class StorageSettings:
    """Immutable storage settings rooted under one configurable data directory."""

    data_root: Path = field(default_factory=lambda: Path(".ria"))
    database_path: Optional[Path] = None
    sqlite_busy_timeout_ms: int = 5000
    blob_store_path: Optional[Path] = None
    blob_shard_depth: int = 2
    blob_shard_width: int = 2
    mirror_root: Optional[Path] = None

    def __post_init__(self) -> None:
        """Resolve paths once and derive unspecified storage locations."""
        data_root = Path(self.data_root).expanduser().resolve()
        object.__setattr__(self, "data_root", data_root)
        object.__setattr__(
            self,
            "database_path",
            (
                Path(self.database_path).expanduser().resolve()
                if self.database_path is not None
                else data_root / "ria.db"
            ),
        )
        object.__setattr__(
            self,
            "blob_store_path",
            (
                Path(self.blob_store_path).expanduser().resolve()
                if self.blob_store_path is not None
                else data_root / "blobs"
            ),
        )
        object.__setattr__(
            self,
            "mirror_root",
            (
                Path(self.mirror_root).expanduser().resolve()
                if self.mirror_root is not None
                else data_root / "mirrors"
            ),
        )


@dataclass(frozen=True, slots=True)
class GitSettings:
    """Immutable Git subprocess settings container."""

    executable: str = "git"
    command_timeout_seconds: float = 60.0
    max_stderr_capture: int = 4096
    max_blob_bytes: int = 10 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class Settings:
    """Immutable application settings container."""

    environment: str = "development"
    workspace_base_dir: Path = field(default_factory=lambda: Path(".ria/workspaces"))
    sqlite_db_path: str = ".ria/ria.db"
    git_timeout_seconds: float = 60.0
    max_file_size_bytes: int = 2 * 1024 * 1024
    default_tenant_id: str = "default"
    git: GitSettings = field(default_factory=GitSettings)
    observability: ObservabilitySettings = field(default_factory=ObservabilitySettings)
    storage: StorageSettings = field(default_factory=StorageSettings)

    @property
    def is_production(self) -> bool:
        """Whether these settings identify a production runtime."""
        return self.environment == "production"

    def ensure_directories(self) -> None:
        """Ensure all required storage and workspace directories exist."""
        try:
            self.workspace_base_dir.mkdir(parents=True, exist_ok=True)
            self.storage.data_root.mkdir(parents=True, exist_ok=True)
            self.storage.database_path.parent.mkdir(parents=True, exist_ok=True)
            self.storage.blob_store_path.mkdir(parents=True, exist_ok=True)
            self.storage.mirror_root.mkdir(parents=True, exist_ok=True)
        except OSError as err:
            raise ConfigurationError(
                "Unable to create required application directories",
                {"error": str(err)},
            ) from err

    @classmethod
    def load_from_env(cls) -> "Settings":
        """Load settings from environment variables with sensible defaults."""
        env = _EnvironmentValidationBoundary(
            environment=os.getenv("RIA_ENV", "development")
        ).environment
        workspace_str = os.getenv("RIA_WORKSPACE_DIR", ".ria/workspaces")
        db_path = os.getenv("RIA_SQLITE_DB_PATH", ".ria/ria.db")
        git_timeout_str = os.getenv("RIA_GIT_TIMEOUT", "60.0")
        max_size_str = os.getenv("RIA_MAX_FILE_SIZE", str(2 * 1024 * 1024))

        try:
            git_timeout = float(git_timeout_str)
            max_size = int(max_size_str)
        except ValueError as err:
            raise ConfigurationError(
                f"Invalid numeric configuration in environment: {err}"
            ) from err

        return cls(
            environment=env,
            workspace_base_dir=Path(workspace_str),
            sqlite_db_path=db_path,
            git_timeout_seconds=git_timeout,
            max_file_size_bytes=max_size,
        )

    @classmethod
    def create_testing(cls, tmp_dir: Path) -> "Settings":
        """Factory for an isolated test environment with observable operations."""
        return cls(
            environment="test",
            workspace_base_dir=tmp_dir / "workspaces",
            sqlite_db_path=":memory:",
            git_timeout_seconds=10.0,
            observability=ObservabilitySettings(metrics_enabled=True),
            storage=StorageSettings(data_root=tmp_dir),
        )

    @classmethod
    def for_testing(cls, tmp_dir: Path) -> "Settings":
        """Alias for create_testing."""
        return cls.create_testing(tmp_dir)
